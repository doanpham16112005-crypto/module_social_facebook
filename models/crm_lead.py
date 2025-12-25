# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class CrmLead(models.Model):
    """
    Mở rộng crm.lead để link với Facebook conversations.
    """
    _inherit = 'crm.lead'
    
    # Link to Facebook
    facebook_conversation_id = fields.Many2one(
        'social.message',
        string='Facebook Conversation',
        ondelete='set null',
        help='Conversation Messenger tạo ra lead này',
    )
    facebook_user_id = fields.Char(
        string='Facebook User ID',
        help='PSID của khách hàng',
    )
    
    # Statistics
    messenger_message_count = fields.Integer(
        string='Messenger Messages',
        compute='_compute_messenger_stats',
        help='Số tin nhắn trong conversation',
    )
    
    def _compute_messenger_stats(self):
        """Tính số tin nhắn Messenger"""
        for lead in self:
            if lead.facebook_conversation_id:
                messages = self.env['social.message'].search_count([
                    ('conversation_id', '=', lead.facebook_conversation_id.id)
                ])
                lead.messenger_message_count = messages
            else:
                lead.messenger_message_count = 0
    
    def action_view_messenger_conversation(self):
        """Xem conversation Messenger"""
        self.ensure_one()
        if not self.facebook_conversation_id:
            return {'type': 'ir.actions.act_window_close'}
        
        return {
            'name': _('Messenger Conversation'),
            'type': 'ir.actions.act_window',
            'res_model': 'social.message',
            'res_id': self.facebook_conversation_id.id,
            'view_mode': 'form',
            'target': 'current',
        }