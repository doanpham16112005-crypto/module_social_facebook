from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
import re

_logger = logging.getLogger(__name__)


class SocialMessage(models.Model):
    """
    Model quản lý Facebook Messenger conversations.
    
    ✅ UPGRADED VERSION với đầy đủ field cho chatbot nâng cao
    """
    
    _name = 'social.message'
    _description = 'Social Message / Conversation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'facebook_user_id'
    
    # =========================================================================
    # BASIC FIELDS
    # =========================================================================
    
    facebook_user_id = fields.Char(
        string='Facebook User ID (PSID)',
        required=True,
        index=True,
        help='Page-Scoped User ID from Facebook',
    )
    
    account_id = fields.Many2one(
        'social.account',
        string='Facebook Page',
        required=True,
        ondelete='cascade',
        index=True,
    )
    
    message_id = fields.Char(
        string='Message ID',
        index=True,
        help='Facebook Message ID',
    )
    
    message = fields.Text(
        string='Message Content',
    )
    
    is_from_customer = fields.Boolean(
        string='From Customer',
        default=True,
    )
    
    attachments = fields.Text(
        string='Attachments',
        help='JSON data',
    )
    
    created_date = fields.Datetime(
        string='Created Date',
        default=fields.Datetime.now,
        index=True,
    )
    
    last_message_date = fields.Datetime(
        string='Last Message',
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    
    # =========================================================================
    # ✅ CHATBOT FIELDS
    # =========================================================================
    
    chatbot_state = fields.Selection([
        ('idle', 'Idle'),
        ('ask_name', 'Asking Name'),
        ('ask_phone', 'Asking Phone'),
        ('ask_address', 'Asking Address'),  # ✅ MỚI
        ('show_products', 'Showing Products'),
        ('ask_quantity', 'Asking Quantity'),  # ✅ MỚI
        ('confirm_order', 'Confirming Order'),
        ('completed', 'Completed'),
    ], string='Chatbot State', default='idle', tracking=True, index=True)
    
    customer_name = fields.Char(
        string='Customer Name',
        tracking=True,
        help='Tên khách hàng (đã chuẩn hóa)',
    )
    
    customer_phone = fields.Char(
        string='Customer Phone',
        tracking=True,
        help='Số điện thoại (đã chuẩn hóa về format 0XXXXXXXXX)',
    )
    
    # ✅ THÊM VÀO CUỐI PHẦN CHATBOT FIELDS (sau chatbot_state)
    
    customer_address = fields.Char(
        string='Customer Address',
        tracking=True,
        help='Địa chỉ giao hàng',
    )
    
    product_quantity = fields.Integer(
        string='Product Quantity',
        default=1,
        help='Số lượng sản phẩm khách đặt',
    )
    
    selected_product_ids = fields.Many2many(
        'social.messenger.product',
        'social_message_product_rel',
        'message_id',
        'product_id',
        string='Selected Products',
    )
    
    # ✅ NÂNG CẤP 7: Cooldown field
    cooldown_until = fields.Datetime(
        string='Cooldown Until',
        help='Thời gian kết thúc cooldown sau khi hoàn tất đơn hàng (tránh spam)',
    )
    
    # =========================================================================
    # CRM & SALES INTEGRATION
    # =========================================================================
    
    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        ondelete='set null',
        tracking=True,
    )
    
    messenger_order_id = fields.Many2one(
        'social.messenger.order',
        string='Messenger Order',
        ondelete='set null',
        tracking=True,
    )
    
    conversation_id = fields.Many2one(
        'social.conversation',
        string='Conversation',
        ondelete='cascade',
    )
    
    # =========================================================================
    # CONSTRAINTS
    # =========================================================================
    
    _sql_constraints = [
        ('facebook_user_account_uniq',
         'UNIQUE(facebook_user_id, account_id)',
         'Conversation already exists for this user and page!'),
    ]