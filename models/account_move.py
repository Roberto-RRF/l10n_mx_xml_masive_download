from odoo import fields, models
from odoo.exceptions import UserError
import base64

class AccountMove(models.Model):
    _inherit = 'account.move'


    # This method was moved to DownloadedXmlSat --> delete later 
    def relate_download(self):
        domain = [('state', '=', 'draft')]
        to_relate = self.env['account.edi.downloaded.xml.sat'].search(domain)
        
        for download in to_relate: 
            domain = [('state', 'not in', ['cancel', 'draft']), ('l10n_mx_edi_cfdi_uuid', '=', download.name)]
            move = self.env['account.move'].search(domain)
            if len(move) == 1:
                download.write({'invoice_id':move.id, 'state': move.state})
            else:
                download.write({'state': 'error'})

    def generate_pdf_attatchment(self):
        invoice_report = self.env.ref('account.account_invoices')
        data_record = base64.b64encode(
            self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                invoice_report, [self.id], data=None)[0])
        ir_values = {
            'name': 'Invoice ' + self.name,
            'type': 'binary',
            'datas': data_record,
            'store_fname': data_record,
            'mimetype': 'application/pdf',
            'res_model': 'account.move',
            'res_id': self.id,
        }
       
        self.env['ir.attachment'].sudo().create(ir_values)

"""    def create_edi_document_from_attatchment(self):
        self.write({
            'state': 'posted',
            'posted_before': True,
        })
        posted = self

        edi_document_vals_list = []
        for move in posted:
            for edi_format in move.journal_id.edi_format_ids:
                move_applicability = edi_format._get_move_applicability(move)
            
                if move_applicability:
                    edi_content = move.attachment_ids.filtered(lambda m: m.mimetype == 'application/xml')
                    if edi_content:
                        edi_document_vals_list.append({
                            'edi_format_id': edi_format.id,
                            'move_id': move.id,
                            'state': 'sent',
                            'attachment_id': edi_content.id,
                        })

        res = self.env['account.edi.document'].create(edi_document_vals_list)
        return posted

"""
