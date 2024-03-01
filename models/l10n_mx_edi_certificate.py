# -*- coding: utf-8 -*-

from odoo import api, fields, models

class Certificate(models.Model):
    _inherit = 'l10n_mx_edi.certificate'

    # Field to know if it is a FIEL certificate or a Certificado de Sello Digital certificate
    l10n_mx_fiel = fields.Boolean("FIEL")

    # Field to store certificate file name
    content_name = fields.Char("Nombre del Archivo")

    # Field to store private key file name
    key_name = fields.Char("Nombre del Archivo")

    # Field to store comapny id, this is useful in multi-company environments
    l10n_mx_company_id = fields.Many2one('res.company', string='Company', ondelete='cascade', index=True, default=lambda self: self.env.company.id)