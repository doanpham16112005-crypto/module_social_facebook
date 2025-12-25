from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class SocialComment(models.Model):
    _name = 'social.comment'
    _description = 'Facebook Comment'
    _order = 'comment_date desc'

    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    post_id = fields.Many2one('social.post', string='Post', required=True, ondelete='cascade')
    facebook_comment_id = fields.Char(string='Facebook Comment ID', required=True)
    author_name = fields.Char(string='Author', required=True)
    author_facebook_id = fields.Char(string='Author FB ID')
    message = fields.Text(string='Message', required=True)
    comment_date = fields.Datetime(string='Date', required=True, default=fields.Datetime.now)
    parent_id = fields.Many2one('social.comment', string='Parent Comment')
    is_hidden = fields.Boolean(string='Hidden', default=False)
    is_spam = fields.Boolean(string='Spam', default=False)
    reply_text = fields.Text(string='Reply')
    replied = fields.Boolean(string='Replied', default=False)
    company_id = fields.Many2one('res.company', related='post_id.company_id', store=True)
    
    @api.depends('author_name', 'message')
    def _compute_display_name(self):
        for comment in self:
            preview = comment.message[:50] + '...' if len(comment.message or '') > 50 else comment.message
            comment.display_name = f"{comment.author_name}: {preview}"
    
    def action_reply(self):
        self.ensure_one()
        if not self.reply_text:
            raise UserError(_('Please enter a reply message!'))
        try:
            url = f'https://graph.facebook.com/v18.0/{self.facebook_comment_id}/comments'
            data = {'access_token': self.post_id.account_id.access_token, 'message': self.reply_text}
            response = requests.post(url, data=data, timeout=30)
            if response.status_code == 200:
                self.replied = True
                return {'type': 'ir.actions.client', 'tag': 'display_notification',
                        'params': {'title': _('Success'), 'message': _('Reply sent!'), 'type': 'success'}}
            else:
                raise UserError(_('Failed to reply: %s') % response.text)
        except Exception as e:
            raise UserError(_('Error: %s') % str(e))
    
    def action_hide(self):
        self.ensure_one()
        self.is_hidden = True
    
    def action_mark_spam(self):
        self.ensure_one()
        self.is_spam = True