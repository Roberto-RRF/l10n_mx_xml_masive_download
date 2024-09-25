from odoo import api, fields, models, tools
from odoo.exceptions import UserError

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def create_edi_document_from_attatchment(self):
        print("HOLA")
        edi_cfdi33 = self.env['account.edi.format'].search([('code','=','cfdi_3_3')], limit=1)
        edi_document_vals_list = []
        print(self.attachment_ids)
        for payment in self:
            xml_file = payment.attachment_ids.filtered(lambda m: m.mimetype == 'application/xml')
            if xml_file:
                edi_document_vals_list.append({
                    'edi_format_id': edi_cfdi33.id,
                    'move_id': payment.move_id.id,
                    'state': 'sent',
                    'attachment_id': xml_file.id,
                })
        res = self.env['account.edi.document'].create(edi_document_vals_list)