from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    can_delete_xml = fields.Boolean(string='Capacidad de eliminar XML o lotes XML SAT', default=True)
    can_access_xml_models = fields.Boolean(string='Capacidad de acceder a XML SAT', default=True)