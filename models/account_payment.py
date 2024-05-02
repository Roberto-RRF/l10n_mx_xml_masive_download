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
   
            edi_data = {
                           # 'name' : uuid_name+'.xml',
                           'state' : 'payment_sent',
                           'sat_state' : 'not_defined',
                           'message': '',
                           'datetime': fields.Datetime.now(),
                           'attachment_uuid': self.name,
                           'attachment_id' : self.id,
                           'move_id'    : self.move_id.id,
                        }
            new_edi_doc = edi.create(edi_data)

            #### Asociando las Facturas ####
            invoice_rel_ids = []
            #### Facturas de Cliente ####
            if self.reconciled_invoice_ids:
                invoice_rel_ids = self.reconciled_invoice_ids.ids
            #### Facturas de Proveedor ####
            if self.reconciled_bill_ids:
                invoice_rel_ids = self.reconciled_bill_ids.ids

            new_edi_doc.invoice_ids = [(6,0, invoice_rel_ids)] 