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
from io import BytesIO
import xml.etree.ElementTree as ET
from datetime import datetime
 
#ydktJDzg4Fr9nh

class DownloadedXmlSat(models.Model):
    _name = "account.edi.downloaded.xml.sat"
    _description = "Account Edi Download From SAT Web Service"
    _check_company_auto = True
  
    name = fields.Char(string="UUID", required=True, index='trigram')
    active_company_id = fields.Integer(string='Active Company ID', compute='_compute_active_company_id')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id) 
    partner_id = fields.Many2one('res.partner') # Cliente/Proveedor
    invoice_id = fields.Many2one('account.move') # Factura
    xml_file = fields.Binary(string='XML File') # Archivo XML
    cfdi_type = fields.Selection([('emitidos', 'Emitidos'), ('recibidos', 'Recibidos')], string='Type', required=True, default='emitidos') 
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
    stamp_date =  fields.Char(string="Stamped Date", required=True)
    xml_file_name = fields.Char(string='XML File Name')
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], string='State', default='draft')
    state = fields.Selection(
        selection=[
            ('not_imported', 'No Importado'),
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('cancel', 'Cancelled'),
            ('error_relating', 'Error Relating'),
        ],
        string='Status',
        default='draft',
    )
    payment_method = fields.Selection([('PPD','PPD'),('PUE','PUE')], string='Payment Method', required=True)
    sub_total = fields.Float(string="Sub Total", required=True)
    amount_total = fields.Float(string="Total", required=True)
    document_type = fields.Selection([
        ('I', 'Ingreso'),
        ('E', 'Egreso'),
        ('T', 'Traslado'),
        ('N', 'Nomina'),
        ('P', 'Pago'),
    ], string='Tipo de Documento')

    def _compute_active_company_id(self):
        self.active_company_id = self.env.company.id

    downloaded_product_id = fields.One2many(
        'account.edi.downloaded.xml.sat.products',
        'downloaded_invoice_id',
        string='Downloaded product ID',)  
    
    def relate_download(self): 
        for item in self:
            move = self.env['account.move'].search([('sat_uuid', '=', item.name)], limit=1)
            if move:
                item.write({'invoice_id': move.id, 'state': move.state})

    
    def action_import_invoice(self):
        for item in self:
            #if item.state != 'no_imported':
            #    raise UserError("El XML ya fue importado")
            root = ET.fromstring(base64.b64decode(item.xml_file))
            receptor = root.find('.//cfdi:Receptor', namespaces={'cfdi': 'http://www.sat.gob.mx/cfd/4'})

            if root.attrib.get('Serie') and root.attrib.get('Folio'):
                ref = root.attrib.get('Serie')+"/"+root.attrib.get('Folio')
            else:
                ref = False

            account_move_dict = {
                'ref': ref,
                'invoice_date': item.stamp_date,
                'date': item.stamp_date,
                'move_type':'in_invoice',
                'partner_id': item.partner_id.id,
                'company_id': item.company_id.id,
                'invoice_line_ids': [],
                'l10n_mx_edi_cfdi_uuid': item.name,
                'l10n_mx_edi_usage': receptor.attrib.get('UsoCFDI'),
                'l10n_mx_edi_payment_policy': root.attrib.get('MetodoPago'),
                'l10n_mx_edi_payment_method_id': self.env['l10n_mx_edi.payment.method'].search([('code', '=', root.attrib.get('FormaPago'))]).id,
                'currency_id': self.env['res.currency'].search([('name', '=', root.attrib.get('Moneda'))],limit=1).id,
            }

            for concepto in item.downloaded_product_id:
                    account_move_dict['invoice_line_ids'].append((0, 0, {
                    'product_id': concepto.product_rel.id,
                    'name': concepto.description,
                    'product_id': concepto.product_rel.id,
                    'quantity': concepto.quantity,
                    'price_unit': concepto.unit_value,
                    'credit': concepto.total_amount,
                }))
            account_move = self.env['account.move'].create(account_move_dict)
            item.write({'invoice_id': account_move.id, 'state': 'draft'})
            
            # Add attachments
            account_move.generate_pdf_attatchment()

            attachment_values = {
                'name': self.xml_file_name,  # Name of the XML file
                'datas': self.xml_file,  # Read XML file content
                'res_model': 'account.move',
                'res_id': account_move.id,
                'mimetype': 'application/xml',
            }
            self.env['ir.attachment'].create(attachment_values)
            

    
class AccountEdiApiDownload(models.Model):
    _name = 'account.edi.api.download'
    _description = "Account Edi Download From SAT Web Service"

    @api.model
    def _get_default_vat(self):
        # Get TAX ID from the company that is currently logged in
        return self.env.company.vat
    
    # Fields
    name = fields.Char(string='Name',  index=True) #required=True,
    vat = fields.Char(string='Tax ID',  default=_get_default_vat ,help="The Tax Identification Number. Complete it if the contact is subjected to government taxes. Used in some legal statements.")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, readonly = True)
    date_start = fields.Date(string='Start Date', required=True, default=fields.Date.today())
    date_end = fields.Date(string='End Date', required=True, default=fields.Date.today())
    cfdi_type = fields.Selection([('emitidos', 'Emitidos'), ('recibidos', 'Recibidos')], string='Type', required=True, default='emitidos')
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
    #stamp_date =  fields.Char(string="Stamped Date", required=True)

    def _get_default_certificates(self):
        domain = [('date_start', '<=', fields.Date.today()), ('date_end', '>=', fields.Date.today()),('l10n_mx_fiel', '=', True),('l10n_mx_company_id', '=', self.env.company.id)]
        cer = self.env['l10n_mx_edi.certificate'].search(domain, limit=1)
        # raise UserError(str(cer))
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

                    # Buscamos a ver si ya se relaciono el producto
                    domain = [
                        ('sat_id', '=', clave_prod_serv),
                        ('description', '=', descripcion), 
                        ('downloaded_invoice_id.partner_id', '!=', False)
                        ]
                    product_id = self.env['account.edi.downloaded.xml.sat.products'].search(domain, limit=1)
                    
                    # Si no se encontro el producto, nos aseguramos de que no se relacione
                    if not product_id.product_rel:
                        product_id = False
                    

                    # Create a dictionary for each concepto and append it to the list
                    concepto_info = {
                        'sat_id': clave_prod_serv,
                        'quantity': cantidad,
                        'product_metrics': clave_unidad,
                        'description': descripcion,
                        'unit_value': valor_unitario,
                        'total_amount': importe,
                        'downloaded_invoice_id': False,
                        'product_rel': product_id.id if product_id else False,
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
            # EMITIDOS
            # print("Token: "+token)
            # print("RFC: "+RFC)
            
            solicitud = descarga.solicitar_descarga(
                token, RFC, FECHA_INICIAL, FECHA_FINAL, rfc_emisor=RFC, tipo_solicitud='CFDI')
        else:
            # RECIBIDOS
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
                # Estado aceptado, esperar 40 segundos y volver a verificar
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
                                'amount_total': cfdi_infos.get('amount_total') if cfdi_infos.get('amount_total') else '0.0'
                            }

                            # Creamos los productos del xml
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
    tax_id = fields.Many2one('account.tax')

    downloaded_invoice_id = fields.Many2one(
        'account.edi.downloaded.xml.sat',
        string='Downloaded product ID',
        ondelete="cascade")
        

