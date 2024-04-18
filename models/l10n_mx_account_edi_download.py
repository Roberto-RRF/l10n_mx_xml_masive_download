# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, tools
from odoo.exceptions import UserError, ValidationError
from lxml import etree
from lxml.objectify import fromstring
import base64
import zipfile
import time
from cfdiclient import (Autenticacion, DescargaMasiva, Fiel, SolicitaDescarga,
                        VerificaSolicitudDescarga)
from odoo.addons.l10n_mx_edi.models.l10n_mx_edi_document import (
    CFDI_CODE_TO_TAX_TYPE,
)
from io import BytesIO
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher 

USO_CFDI  = [
    ("G01", "Adquisición de mercancías"),
    ("G02", "Devoluciones, descuentos o bonificaciones"),
    ("G03", "Gastos en general"),
    ("101", "Construcciones"),
    ("102", "Mobiliario y equipo de oficina por inversiones"),
    ("103", "Equipo de transporte"),
    ("104", "Equipo de cómputo y accesorios"),
    ("105", "Dados, troqueles, moldes, matrices y herramental"),
    ("106", "Comunicaciones telefónicas"),
    ("107", "Comunicaciones satelitales"),
    ("108", "Otra maquinaria y equipo"),
    ("D01", "Honorarios médicos, dentales y gastos hospitalarios"),
    ("D02", "Gastos médicos por incapacidad o discapacidad"),
    ("D03", "Gastos funerales"),
    ("D04", "Donativos"),
    ("D05", "Intereses reales efectivamente pagados por créditos hipotecarios (casa habitación)"),
    ("D06", "Aportaciones voluntarias al SAR"),
    ("D07", "Primas por seguros de gastos médicos"),
    ("D08", "Gastos de transportación escolar obligatoria"),
    ("D09", "Depósitos en cuentas para el ahorro, primas que tengan como base planes de pensiones"),
    ("D10", "Pagos por servicios educativos (colegiaturas)"),
    ("CP01", "Pagos"),
    ("CN01", "Nómina"),
    ("S01", "Sin Efectos Fiscales"),
]
 
#ydktJDzg4Fr9nh
#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

class DownloadedXmlSat(models.Model):
    _name = "account.edi.downloaded.xml.sat"
    _description = "Account Edi Download From SAT Web Service"
    _check_company_auto = True
  
    name = fields.Char(string="UUID", required=True, index='trigram')
    active_company_id = fields.Integer(string='Empresa', compute='_compute_active_company_id')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id) 
    partner_id = fields.Many2one('res.partner') # Cliente/Proveedor
    invoice_id = fields.Many2one('account.move') # Factura
    xml_file = fields.Binary(string='Archivo XML') # Archivo XML
    cfdi_type = fields.Selection([('recibidos', 'Recibidos'),('emitidos', 'Emitidos'), ], string='Tipo', required=True, default='emitidos') 
    batch_id = fields.Many2one(
        comodel_name='account.edi.api.download',
        string='Batch',
        required=True,
        readonly=True,
        index=True,
        auto_join=True,
        ondelete="cascade",
        check_company=True,
    )
    stamp_date =  fields.Date(string="Fecha de Estampado", required=True)
    xml_file_name = fields.Char(string='Nombre archivo XML')
    serie = fields.Char(string="Serie Factura")
    folio = fields.Char(string="Folio Factura")
    divisa = fields.Char(string="Divisa en Factura")
    state = fields.Selection(
        selection=[
            ('not_imported', 'No Importado'),
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('cancel', 'Cancelled'),
            ('error_relating', 'Error Relacionando'),
        ],
        string='Status',
        default='draft',
    )
    payment_method = fields.Selection([('PPD','PPD'),('PUE','PUE')], string='Metodo de Pago')
    sub_total = fields.Float(string="Sub Total", required=True)
    amount_total = fields.Float(string="Total", required=True)
    document_type = fields.Selection([
        ('I', 'Ingreso'),
        ('E', 'Egreso'),
        ('T', 'Traslado'),
        ('N', 'Nomina'),
        ('P', 'Pago'),
    ], string='Tipo de Documento')
    cfdi_usage = fields.Selection(USO_CFDI, string="Uso CFDI")
    imported = fields.Boolean(string="Importado", default=False)
    downloaded_product_id = fields.One2many(
        'account.edi.downloaded.xml.sat.products',
        'downloaded_invoice_id',
        string='Downloaded product ID',)  

    def _compute_active_company_id(self):
        self.active_company_id = self.env.company.id

    def relate_download(self): 
        for item in self:
            move = self.env['account.move'].search([('stored_sat_uuid', '=', item.name)], limit=1)
            if move:
                item.write({'invoice_id': move.id, 'state': move.state})
    
    def generate_pdf_attatchment(self, account_id):
        datas = {
            'partner_id':self.partner_id,
            'cfdi_type':self.cfdi_type,
            'company_id':self.company_id,
            'payment_method':self.payment_method,
            'serie':self.serie,
            'folio':self.folio, 
            'divisa':self.divisa,
            'name':self.name,
            'stamp_date':self.stamp_date,
            'document_type':self.document_type,
            'downloaded_product_id':self.downloaded_product_id

        }
        result, format = self.env["ir.actions.report"]._render_qweb_pdf('l10n_mx_xml_masive_download.report_product', [self.id], datas)

        result = base64.b64encode(result)

        ir_values = {
            'name': 'Invoice ' + self.name,
            'type': 'binary',
            'datas': result,
            'store_fname': 'Factura ' + self.name + '.pdf',
            'mimetype': 'application/pdf',
            'res_model': 'account.move',
            'res_id': account_id,
        }
       
        self.env['ir.attachment'].create(ir_values)

    def action_import_invoice(self):
        for item in self:

            account_move_dict = {
                'ref': self.serie+"/"+self.folio,
                'invoice_date': item.stamp_date,
                'date': item.stamp_date,
                'move_type':'in_invoice' if self.cfdi_type == 'recividos' else 'out_invoice',
                'partner_id': item.partner_id.id,
                'company_id': item.company_id.id,
                'invoice_line_ids': [],
                'currency_id': self.env['res.currency'].search([('name', '=',self.divisa)],limit=1).id,
                'l10n_edi_imported_from_sat': True,
                'xml_imported_id': item.id
            }

            for concepto in item.downloaded_product_id:
                    account_move_dict['invoice_line_ids'].append((0, 0, {
                    'product_id': concepto.product_rel.id,
                    'name': concepto.description,
                    'product_id': concepto.product_rel.id,
                    'quantity': concepto.quantity,
                    'price_unit': concepto.unit_value,
                    'credit': concepto.total_amount,
                    'tax_ids': concepto.tax_id,
                    'downloaded_product_rel': concepto.id, 
                }))
            account_move = self.env['account.move'].create(account_move_dict)
            item.write({'invoice_id': account_move.id, 'state': 'draft'})

            
            self.generate_pdf_attatchment(account_move.id)

            attachment_values = {
                'name': self.xml_file_name,  # Name of the XML file
                'datas': self.xml_file,  # Read XML file content
                'res_model': 'account.move',
                'res_id': account_move.id,
                'mimetype': 'application/xml',
            }
            self.env['ir.attachment'].create(attachment_values)
            account_move.create_edi_document_from_attatchment(self.name)
            #item.write({'imported': True})

    def action_add_payment(self):
        payment = self.env['account.payment'].search([('stored_sat_uuid','=',self.name)], limit=1)
        if payment and payment.status == 'paid':
            attachment_values = {
                'name': self.xml_file_name,  # Name of the XML file
                'datas': self.xml_file,  # Read XML file content
                'res_model': 'account.move',
                'res_id': payment.id,
                'mimetype': 'application/xml',
            }
            self.env['ir.attachment'].create(attachment_values)
            self.write({'imported': True})
    
class AccountEdiApiDownload(models.Model):
    _name = 'account.edi.api.download'
    _description = "Account Edi Download From SAT Web Service"

    @api.model
    def _get_default_vat(self):
        # Get TAX ID from the company that is currently logged in
        return self.env.company.vat
    
    # Fields
    name = fields.Char(string='Nombre',  index=True) 
    vat = fields.Char(string='RFC',  default=_get_default_vat)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, readonly = True)
    date_start = fields.Date(string='Fecha de Comienzo', required=True, default=fields.Date.today())
    date_end = fields.Date(string='Fecha de Finalizacion', required=True, default=fields.Date.today())
    cfdi_type = fields.Selection([('emitidos', 'Emitidos'), ('recibidos', 'Recibidos')], string='Tipo', required=True, default='emitidos')
    state = fields.Selection(
    selection=[
        ('not_imported', 'No importado'),
        ('imported', 'Importado'),
        ('error', 'Error'),
    ],
    string='Status', default='not_imported', readonly=True, 
    )
    xml_sat_ids = fields.One2many(
        'account.edi.downloaded.xml.sat',
        'batch_id',
        string='Downloaded XML SAT',
        copy=True,
        readonly=True,
        #states={'not_imported': [('readonly', False)]},
    )
    xml_count = fields.Integer(string='Delivery Orders', compute='_compute_xml_ids')

    def _get_default_certificates(self):
        cer = self.env.company.l10n_mx_edi_fiel_ids.filtered(lambda x: x.l10n_mx_fiel == True)

        if not cer:
            raise UserError("No existe un certificado activo para el periodo actual")
        else: 
            return cer
        
    @api.depends('xml_sat_ids')
    def _compute_xml_ids(self):
        for xml in self:
            xml.xml_count = len(xml.xml_sat_ids)
        
    def view_xml_sat(self):
         xml_sat_ids = self.xml_sat_ids.ids

         return {
            'type': 'ir.actions.act_window',
            'name': 'XML SAT',
            'res_model': 'account.edi.downloaded.xml.sat',
            'view_mode': 'tree,form',
            'target': 'current',
            'domain': [('id', 'in', xml_sat_ids)]
        }
        
    def action_download(self):

        """
        Function that recives two strings and returns a number 
        from 0 to 1 depending on how similar they are. 
        Used to compare descriptions that have dates or numbers
        """
        def similar(a, b):
            return SequenceMatcher(None, a, b).ratio()
        
        def _l10n_mx_edi_import_cfdi_get_tax_from_node(self, tax_node, is_withholding=False):
            amount = float(tax_node.attrib.get('TasaOCuota')) * (-100 if is_withholding else 100)
            domain = [
                #*self.env['account.journal']._check_company_domain(company_id),
                ('amount', '=', amount),
                ('type_tax_use', '=', 'sale' if self.cfdi_type == 'emitidos' else 'purchase'),
                ('amount_type', '=', 'percent'),
            ]
            tax_type = CFDI_CODE_TO_TAX_TYPE.get(tax_node.attrib.get('Impuesto'))
            if tax_type:
                domain.append(('l10n_mx_tax_type', '=', tax_type))
            taxes = self.env['account.tax'].search(domain, limit=1)
            if not taxes:
                raise UserError("No se encotro un impuesto para el siguiente: "+tax_type+" "+str(amount))
            return taxes[:1]

        """  
        Function that extracts the products from the XML
        return: list of dictionaries with the products
        """
        def get_products(xml_file):
            root = ET.fromstring(xml_file)
            # Define the namespace used in the XML
            ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4'}
            # Find the cfdi:Conceptos element
            conceptos_element = root.find('.//cfdi:Conceptos', namespaces=ns)
            # Initialize an empty list to store dictionaries
            conceptos_list = []
            if conceptos_element is not None:

                # Iterate over cfdi:Concepto elements and extract information
                for concepto_element in conceptos_element.findall('.//cfdi:Concepto', namespaces=ns):
                    clave_prod_serv = concepto_element.get('ClaveProdServ')
                    cantidad = concepto_element.get('Cantidad')
                    clave_unidad = concepto_element.get('ClaveUnidad')
                    descripcion = concepto_element.get('Descripcion')
                    valor_unitario = concepto_element.get('ValorUnitario')
                    importe = concepto_element.get('Importe')

                    taxes = []
                    taxes_ids = []
                    # Buscamos los impuestos
                    impuestos = concepto_element.find('.//cfdi:Impuestos', namespaces=ns)
                    if impuestos is not None:
                    
                        traslados = impuestos.find('.//cfdi:Traslados', namespaces=ns)
                        if traslados is not None:
                            for traslado in traslados.findall('.//cfdi:Traslado', namespaces=ns):
                                taxes.append(_l10n_mx_edi_import_cfdi_get_tax_from_node(self, tax_node=traslado, is_withholding=False, ))
                        retenciones = impuestos.find('.//cfdi:Retenciones', namespaces=ns)
                        if retenciones is not None:
                            for retencion in retenciones.findall('.//cfdi:Retencion', namespaces=ns):
                                taxes.append(_l10n_mx_edi_import_cfdi_get_tax_from_node(self, tax_node=retencion, is_withholding=True))
                    for tax in taxes: 
                        taxes_ids.append(tax.id)
                    # Buscamos a ver si ya se relaciono el producto
                    domain = [
                        ('sat_id', '=', clave_prod_serv),
                        ('downloaded_invoice_id.partner_id', '!=', False)
                        ]
                    products = self.env['account.edi.downloaded.xml.sat.products'].search(domain, limit=1)
                    
                    final_product = False
                    if products:
                        for product in products:
                            if similar(descripcion, product.description) > 0.8:
                                final_product=product.product_rel
                                break

                    
                    
                    # Create a dictionary for each concepto and append it to the list
                    concepto_info = {
                        'sat_id': clave_prod_serv,
                        'quantity': cantidad,
                        'product_metrics': clave_unidad,
                        'description': descripcion,
                        'unit_value': valor_unitario,
                        'total_amount': importe,
                        'downloaded_invoice_id': False,
                        'product_rel': final_product.id if final_product else False,
                        'tax_id': taxes_ids if taxes_ids else False,
                    }
                    conceptos_list.append(concepto_info)
                return conceptos_list

        cer = self._get_default_certificates()
        RFC = self._get_default_vat()
        FIEL_CER = base64.b64decode(cer.content)
        FIEL_KEY = base64.b64decode(cer.key)
        FIEL_PAS = cer.password
        FECHA_INICIAL = self.date_start
        FECHA_FINAL = self.date_end

        xml_sat_ids = []

        fiel = Fiel(FIEL_CER, FIEL_KEY, FIEL_PAS)
        auth = Autenticacion(fiel)
        token = auth.obtener_token()
        descarga = SolicitaDescarga(fiel)

        if(self.cfdi_type == 'emitidos'):            
            solicitud = descarga.solicitar_descarga(
                token, RFC, FECHA_INICIAL, FECHA_FINAL, rfc_emisor=RFC, tipo_solicitud='CFDI')
        else:
            solicitud = descarga.solicitar_descarga(
                token, RFC, FECHA_INICIAL, FECHA_FINAL, rfc_receptor=RFC, tipo_solicitud='CFDI' )

        while True:
            token = auth.obtener_token()
            verificacion = VerificaSolicitudDescarga(fiel)
            verificacion = verificacion.verificar_descarga(
                token, RFC, solicitud['id_solicitud'])
            estado_solicitud = int(verificacion['estado_solicitud'])

            # 0, Token invalido.
            # 1, Aceptada
            # 2, En proceso
            # 3, Terminada
            # 4, Error
            # 5, Rechazada
            # 6, Vencida

            if estado_solicitud <= 2:
                # Estado aceptado, esperar n segundos y volver a verificar
                time.sleep(30)
                continue

            elif estado_solicitud >= 4:
                # Si el estatus es 4 o mayor se trata de un error
                self.write({'state': 'error'})
                raise UserError("Error al descargar los CFDI")
                break
            else:
                # Descargar los paquetes
                for paquete in verificacion['paquetes']:
                    descarga = DescargaMasiva(fiel)
                    descarga = descarga.descargar_paquete(token, RFC, paquete)
                    # Decodificar los datos Base64
                    datos_binarios = base64.b64decode(descarga['paquete_b64'])
                    zipData = BytesIO()
                    zipData.write(datos_binarios)
                    myZipFile = zipfile.ZipFile(zipData)
                    for file in myZipFile.filelist:
                        with myZipFile.open(file.filename) as myFile:
                            cfdi_data = myFile.read()
                            try:
                                cfdi_node = fromstring(cfdi_data)
                                
                            except etree.XMLSyntaxError:
                                # Not an xml
                                cfdi_info = {}

                            cfdi_infos = self.env['account.move']._l10n_mx_edi_decode_cfdi_etree(cfdi_node)
                            root = ET.fromstring(cfdi_data)

                            # Verificar que no se duplique el UUID
                            domain = [('name', '=', cfdi_infos.get('uuid'))]
                            if self.env['account.edi.downloaded.xml.sat'].search(domain, limit=1):
                                continue

                            """ cfdi_infos = {}
                            'uuid'
                            'supplier_rfc'
                            'customer_rfc'
                            'amount_total'
                            'cfdi_node'
                            'usage'
                            'payment_method'
                            'bank_account'
                            'sello'
                            'sello_sat'
                            'cadena'
                            'certificate_number'
                            'certificate_sat_number'
                            'expedition'
                            'fiscal_regime'
                            'emission_date_str'
                            'stamp_date'
                            """
                            # Buscar el partner
                            if(self.cfdi_type == 'emitidos'):
                                partner = self.env['res.partner'].search([('vat', '=', cfdi_infos.get('customer_rfc'))], limit=1)
                            else: 
                                partner = self.env['res.partner'].search([('vat', '=', cfdi_infos.get('supplier_rfc'))], limit=1)
                            vals = {
                                'name': cfdi_infos.get('uuid'),
                                'xml_file': base64.b64encode(cfdi_data),
                                'cfdi_type': self.cfdi_type,
                                'company_id': self.company_id.id,
                                'partner_id': partner.id if partner else False,
                                'stamp_date': cfdi_infos.get('stamp_date'),
                                'xml_file_name': myFile.name,
                                'state': 'not_imported',
                                'document_type': root.get('TipoDeComprobante'),
                                'payment_method': cfdi_infos.get('payment_method'),
                                'sub_total': root.get('SubTotal') if root.get('SubTotal') else '0.0',
                                'amount_total': cfdi_infos.get('amount_total') if cfdi_infos.get('amount_total') else '0.0',
                                'serie':root.get('Serie'),
                                'folio':root.get('Folio'),
                                'divisa':root.get('Moneda'),
                                'cfdi_usage': cfdi_infos.get('usage'),
                            }

                            recived = False
                            if(self.cfdi_type == 'recibidos'):
                                recived = True
                            # Creamos los productos del xml
                            # recived: boolean to search type of tax
                            products = get_products(cfdi_data)
                            if products:
                                created_products = self.env['account.edi.downloaded.xml.sat.products'].create(products)
                                vals['downloaded_product_id'] = created_products
                            xml_sat_ids.append((0, 0, vals))
                self.write({'xml_sat_ids': xml_sat_ids,'state': 'imported'})
                break

class DownloadedXmlSatProducts(models.Model):
    _name = "account.edi.downloaded.xml.sat.products"
    _description = "Account Edi Download From SAT Web Service Products"

    sat_id = fields.Char(string="SAT ID", required=True)
    quantity = fields.Float(string="Quantity", required=True)
    product_metrics = fields.Char(string="Clave Unidad", required=True)
    description = fields.Char(string="Descripcion", required=True)
    unit_value = fields.Float(string="Valor Unitario", required=True)
    total_amount = fields.Float(string="Importe", required=True)
    product_rel = fields.Many2one('product.product')
    tax_id = fields.Many2many('account.tax')

    downloaded_invoice_id = fields.Many2one(
        'account.edi.downloaded.xml.sat',
        string='Downloaded product ID',
        ondelete="cascade")
    
