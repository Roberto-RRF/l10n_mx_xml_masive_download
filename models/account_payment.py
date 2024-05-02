from odoo import api, fields, models, tools
from odoo.exceptions import UserError

class AccountPayment(models.Model):
    _inherit = "account.payment"

    def create_edi_document_from_attatchment(self, uuid):

        edi = self.env['l10n_mx_edi.document']
        edi_content = self.attachment_ids.filtered(lambda m: m.mimetype == 'application/xml')
        raise UserError(self.move_id.attachment_ids)
        print(edi_content)
        if edi_content:
            print("Adios")
            edi_data = {
                'state' : 'payment_sent',
                'datetime': fields.Datetime.now(),
                'attachment_uuid':uuid,
                'attachment_id':edi_content.id,
                'move_id': self.id,
            }
            new_edi_doc = edi.create(edi_data)

            # Asociar las facturas
            new_edi_doc.invoice_ids = [(6, 0, [self.id])]