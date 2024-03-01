# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError
import base64
import zipfile
import time
from cfdiclient import (Autenticacion, DescargaMasiva, Fiel, SolicitaDescarga,
                        VerificaSolicitudDescarga)



class AccountEdiDownloadWizard(models.TransientModel):
    _name = 'account.edi.download.wizard'
    _description = 'Account Edi Download Wizard'

    @api.model
    def _get_default_vat(self):
        return self.env.user.company_id.vat
    
    # Fields
    vat = fields.Char(string='Tax ID',  default=_get_default_vat ,help="The Tax Identification Number. Complete it if the contact is subjected to government taxes. Used in some legal statements.")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    date_start = fields.Date(string='Start Date', required=True, default=fields.Date.today())
    date_end = fields.Date(string='End Date', required=True, default=fields.Date.today())
    cfdi_type = fields.Selection([('emitidos', 'Emitidos'), ('recibidos', 'Recibidos')], string='Type', required=True, default='emitidos')

    def _get_default_certificates(self):
        domain = [('date_start', '<=', fields.Date.today()), ('date_end', '>=', fields.Date.today())]
        cer = self.env['l10n_mx_edi.certificate'].search(domain, limit=1)
        if not cer:
            raise UserError("No existe un certificado activo para el periodo actual")
        else: 
            return cer

    def action_download(self):
        cer = self._get_default_certificates()
        RFC = self._get_default_vat()
        FIEL_CER = base64.b64decode(cer.content)
        FIEL_KEY = base64.b64decode(cer.key)
        FIEL_PAS = cer.password
        FECHA_INICIAL = self.date_start
        FECHA_FINAL = self.date_end

        fiel = Fiel(FIEL_CER, FIEL_KEY, FIEL_PAS)
        auth = Autenticacion(fiel)
        token = auth.obtener_token()
        descarga = SolicitaDescarga(fiel)

        if(self.cfdi_type == 'emitidos'):
            # EMITIDOS
            solicitud = descarga.solicitar_descarga(
                token, RFC, FECHA_INICIAL, FECHA_FINAL, rfc_emisor=RFC, tipo_solicitud='CFDI')
        else:
            # RECIBIDOS
            solicitud = descarga.solicitar_descarga(
                token, RFC, FECHA_INICIAL, FECHA_FINAL, rfc_emisor=RFC, tipo_solicitud='CFDI')

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
                # Estado aceptado, esperar 60 segundos y volver a verificar
                time.sleep(60)
                continue

            elif estado_solicitud >= 4:
                # Si el estatus es 4 o mayor se trata de un error
                raise UserError("Error al descargar los CFDI")
                break
            else:
                # Descargar los paquetes
                for paquete in verificacion['paquetes']:
                    descarga = DescargaMasiva(fiel)
                    descarga = descarga.descargar_paquete(token, RFC, paquete)

                    self.write_download()


                    with open('{}.zip'.format(paquete), 'wb') as fp:
                        fp.write(base64.b64decode(descarga['paquete_b64']))
                    # Descomprimir y leer archivos dentro del ZIP
                    with zipfile.ZipFile('{}.zip'.format(paquete), 'r') as zip_ref:
                        # Listar archivos dentro del ZIP
                        archivos_en_zip = zip_ref.namelist()
                    # Iterar sobre los archivos dentro del ZIP
                    for archivo in archivos_en_zip:
                        # Hacer algo con cada archivo, por ejemplo, imprimir su nombre
                        continue
                break
    
    def write_download(self):
        vals = {
            'name': "%s-%s-%s" % (self.cfdi_type, self.date_start.strftime('%y%m%d') , self.date_end.strftime('%y%m%d')),
            'cfdi_type': self.cfdi_type,
            'date_start': self.date_start,
            'date_end': self.date_end,
        } 