from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    create_contact = fields.Boolean(string="Creacion Automatica de Contactos")

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param('l10n_mx_xml_masive_download.create_contact', self.create_contact)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res['create_contact'] = self.env['ir.config_parameter'].sudo().get_param('l10n_mx_xml_masive_download.create_contact')
        return res