from odoo import api, fields, models, tools
from odoo.exceptions import UserError

class AccountPayment(models.Model):
    _inherit = "account.payment"

    def create_edi_document_from_attatchment(self, uuid):

        edi = self.env['l10n_mx_edi.document']
        edi_content = self.attachment_ids.filtered(lambda m: m.mimetype == 'application/xml')
        raise UserError("No existe XML adjunto en el Pago: %s " % self.name)
        print(edi_content)
        if edi_content:
            if len(edi_content)>1:
                edi_content = edi_content[-1]
            print("Adios")
            edi_data = {
                'state' : 'payment_sent',
                'datetime': fields.Datetime.now(),
                'attachment_uuid':uuid,
                'attachment_id':edi_content.id,
                'move_id': self.move_id.id,
            }
            new_edi_doc = edi.create(edi_data)

            # Asociar las facturas
            new_edi_doc.invoice_ids = [(6, 0, [self.id])]