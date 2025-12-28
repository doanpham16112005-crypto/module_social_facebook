# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SocialConversation(models.Model):
    """
    Model quản lý Conversations - Cuộc hội thoại Facebook Messenger.
    
    ✅ NÂNG CẤP: Thêm field lead_amount để hiển thị số tiền CRM Lead
    """
    
    _name = 'social.conversation'
    _description = 'Facebook Messenger Conversation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'last_message_date desc, id desc'
    _rec_name = 'customer_name'
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BASIC FIELDS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    facebook_psid = fields.Char(
        string='Facebook PSID',
        required=True,
        index=True,
        help='Page-Scoped User ID - unique identifier của user trong context của page',
    )
    
    account_id = fields.Many2one(
        'social.account',
        string='Facebook Page',
        required=True,
        ondelete='cascade',
        index=True,
        help='Facebook Page nơi conversation diễn ra',
    )
    
    customer_name = fields.Char(
        string='Customer Name',
        tracking=True,
        help='Tên khách hàng (có thể thu thập từ chatbot)',
    )
    
    customer_phone = fields.Char(
        string='Customer Phone',
        tracking=True,
        help='Số điện thoại khách hàng',
    )
    
    customer_email = fields.Char(
        string='Customer Email',
        tracking=True,
        help='Email khách hàng',
    )
    
    state = fields.Selection([
        ('new', 'New'),
        ('ongoing', 'Ongoing'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ], string='State', default='new', tracking=True)
    
    last_message_date = fields.Datetime(
        string='Last Message',
        default=fields.Datetime.now,
        index=True,
        tracking=True,
    )
    
    last_message_from = fields.Selection([
        ('customer', 'Customer'),
        ('page', 'Page'),
    ], string='Last Message From')
    
    # ✅ BỎ: unread_count (theo yêu cầu 2)
    
    first_response_time = fields.Float(
        string='First Response Time (minutes)',
        help='Thời gian phản hồi tin nhắn đầu tiên',
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RELATIONSHIP FIELDS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    message_ids = fields.One2many(
        'social.message',
        'conversation_id',
        string='Messages',
        help='Tất cả tin nhắn trong conversation này',
    )
    
    # ✅ BỎ: message_count (theo yêu cầu 2)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CRM INTEGRATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    lead_id = fields.Many2one(
        'crm.lead',
        string='CRM Lead',
        ondelete='set null',
        tracking=True,
        help='Lead được tạo từ conversation này',
    )
    
    # ✅ THÊM: Field hiển thị số tiền từ CRM Lead
    lead_amount = fields.Monetary(
        string='Lead Amount',
        compute='_compute_lead_amount',
        store=True,
        currency_field='currency_id',
        help='Số tiền expected revenue từ CRM Lead',
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    
    conversation_id = fields.Char(
        string='Conversation ID',
        help='Facebook Conversation ID (hoặc ID nội bộ)',
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONSTRAINTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    _sql_constraints = [
        ('facebook_psid_account_uniq',
         'UNIQUE(facebook_psid, account_id)',
         'Conversation already exists for this user and page!'),
    ]
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ✅ COMPUTE METHODS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    @api.depends('lead_id', 'lead_id.expected_revenue')
    def _compute_lead_amount(self):
        """✅ Tính số tiền từ CRM Lead"""
        for conv in self:
            if conv.lead_id:
                conv.lead_amount = conv.lead_id.expected_revenue or 0.0
            else:
                conv.lead_amount = 0.0
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ACTION METHODS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def action_mark_resolved(self):
        """Đánh dấu conversation là đã giải quyết"""
        for conv in self:
            conv.write({'state': 'resolved'})
            conv.message_post(
                body=_('Conversation marked as resolved'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
    
    def action_close(self):
        """Đóng conversation"""
        for conv in self:
            conv.write({'state': 'closed'})
            conv.message_post(
                body=_('Conversation closed'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
    
    def action_reopen(self):
        """Mở lại conversation đã đóng"""
        for conv in self:
            conv.write({'state': 'ongoing'})
            conv.message_post(
                body=_('Conversation reopened'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
    
    def action_view_lead(self):
        """Xem CRM lead liên kết"""
        self.ensure_one()
        
        if not self.lead_id:
            raise UserError(_('No lead linked to this conversation'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lead'),
            'res_model': 'crm.lead',
            'res_id': self.lead_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_messages(self):
        """Xem tất cả messages trong conversation"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Messages'),
            'res_model': 'social.message',
            'view_mode': 'tree,form',
            'domain': [('conversation_id', '=', self.id)],
            'context': {'default_conversation_id': self.id},
        }