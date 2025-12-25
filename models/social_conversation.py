# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SocialConversation(models.Model):
    """
    Model quản lý Conversations - Cuộc hội thoại Facebook Messenger.
    
    Mỗi conversation đại diện cho 1 cuộc hội thoại với 1 khách hàng cụ thể (PSID).
    Một conversation chứa nhiều messages (social.message).
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MODEL DEFINITION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _name = 'social.conversation'
    _description = 'Facebook Messenger Conversation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'last_message_date desc, id desc'
    _rec_name = 'customer_name'
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BASIC FIELDS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Conversation Identity
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
    
    # Customer Information
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
    
    # Conversation Status
    state = fields.Selection([
        ('active', 'Active'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ], string='State', default='active', tracking=True)
    
    # Timestamps
    last_message_date = fields.Datetime(
        string='Last Message',
        default=fields.Datetime.now,
        index=True,
        tracking=True,
    )
    
    # Organization
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
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
    
    message_count = fields.Integer(
        string='Message Count',
        compute='_compute_message_count',
        store=True,
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CRM INTEGRATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    lead_id = fields.Many2one(
        'crm.lead',
        string='CRM Lead',
        ondelete='set null',
        tracking=True,
        help='Lead được tạo từ conversation này khi có purchase intent',
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
    # COMPUTE METHODS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    @api.depends('message_ids')
    def _compute_message_count(self):
        """Đếm số lượng messages"""
        for conv in self:
            conv.message_count = len(conv.message_ids)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CRM INTEGRATION METHODS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _check_purchase_intent(self, message):
        """
        Kiểm tra nếu tin nhắn thể hiện ý định mua hàng.
        Chỉ tạo/update lead khi khách hàng xác nhận quyết định mua.
        
        Args:
            message (social.message): Message record cần kiểm tra
        """
        self.ensure_one()
        
        message_content = (message.message or '').lower().strip()
        
        # Danh sách keyword mua hàng
        purchase_keywords = [
            'mua', 'đặt hàng', 'order', 'buy', 
            'muốn mua', 'đặt mua', 'book', 'booking'
        ]
        
        # Kiểm tra có keyword mua hàng không
        has_purchase_intent = any(
            keyword in message_content 
            for keyword in purchase_keywords
        )
        
        if not has_purchase_intent:
            return
        
        _logger.info(f"🛒 Purchase intent detected in conversation {self.id}")
        
        # Tạo hoặc cập nhật CRM lead
        self._create_or_update_lead(message)
    
    def _create_or_update_lead(self, message):
        """
        Tạo lead mới hoặc cập nhật lead hiện có khi phát hiện purchase intent.
        
        Args:
            message (social.message): Message trigger việc tạo/update lead
        """
        self.ensure_one()
        
        Lead = self.env['crm.lead']
        
        # Nếu đã có lead → cập nhật
        if self.lead_id:
            lead = self.lead_id
            
            # Thêm message vào chatter
            lead.message_post(
                body=_(
                    "<strong>Purchase intent detected in Facebook Messenger</strong><br/>"
                    "Customer message: <em>%s</em>"
                ) % (message.message or ''),
                message_type='comment',
                subtype_xmlid='mail.mt_comment'
            )
            
            # Cập nhật stage nếu chưa won/lost
            if lead.probability < 100 and lead.probability != 0:
                # Tìm stage "Qualified"
                qualified_stage = self.env['crm.stage'].search([
                    '|',
                    ('name', 'ilike', 'qualified'),
                    ('name', 'ilike', 'qualification')
                ], limit=1)
                
                if qualified_stage:
                    lead.write({
                        'stage_id': qualified_stage.id,
                        'probability': 60,
                    })
            
            _logger.info(f"✅ Updated existing lead {lead.id} with purchase intent")
            
        else:
            # Tạo lead mới
            lead_vals = {
                'name': _('Facebook Lead - %s') % (
                    self.customer_name or self.facebook_psid
                ),
                'type': 'opportunity',
                'contact_name': self.customer_name,
                'phone': self.customer_phone,
                'description': _(
                    "Lead created from Facebook Messenger conversation\n"
                    "Customer PSID: %s\n"
                    "Last message: %s\n"
                    "Purchase intent detected at: %s"
                ) % (
                    self.facebook_psid,
                    message.message or '',
                    fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ),
                'company_id': self.company_id.id,
            }
            
            # Tìm Facebook source
            source = self.env['utm.source'].search([
                ('name', '=', 'Facebook')
            ], limit=1)
            if not source:
                source = self.env['utm.source'].create({'name': 'Facebook'})
            lead_vals['source_id'] = source.id
            
            # Tìm stage "New" hoặc "Qualified"
            new_stage = self.env['crm.stage'].search([
                '|',
                ('name', 'ilike', 'new'),
                ('name', 'ilike', 'qualified')
            ], limit=1)
            
            if new_stage:
                lead_vals['stage_id'] = new_stage.id
                lead_vals['probability'] = (
                    20 if 'new' in new_stage.name.lower() else 60
                )
            
            # Tạo lead
            lead = Lead.create(lead_vals)
            
            # Link lead với conversation
            self.write({'lead_id': lead.id})
            
            # Thêm message vào lead chatter
            lead.message_post(
                body=_(
                    "<strong>Lead created from Facebook Messenger</strong><br/>"
                    "Customer message: <em>%s</em><br/>"
                    "<a href='/web#id=%s&model=social.conversation&view_type=form'>"
                    "View Conversation</a>"
                ) % (message.message or '', self.id),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"✅ Created new lead {lead.id} from conversation {self.id}")
        
        # Cập nhật conversation state
        if self.state == 'active':
            self.write({'state': 'in_progress'})
        
        return lead
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ACTION METHODS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
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
    
    def action_create_lead(self):
        """Tạo lead thủ công"""
        self.ensure_one()
        
        if self.lead_id:
            raise UserError(_('Lead already exists for this conversation'))
        
        # Tạo lead với message trigger giả
        fake_message = self.env['social.message'].create({
            'conversation_id': self.id,
            'account_id': self.account_id.id,
            'message': '[Manual lead creation]',
            'is_from_customer': True,
            'company_id': self.company_id.id,
        })
        
        lead = self._create_or_update_lead(fake_message)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Lead created successfully!'),
                'type': 'success',
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'crm.lead',
                    'res_id': lead.id,
                    'view_mode': 'form',
                }
            }
        }