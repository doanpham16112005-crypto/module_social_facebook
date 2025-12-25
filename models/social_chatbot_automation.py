# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SocialChatbotAutomation(models.Model):
    """
    Model quản lý Chatbot Automation Rules.
    
    Mỗi rule định nghĩa:
    - Trigger keywords: Từ khóa kích hoạt
    - Response text: Nội dung phản hồi tự động
    - Priority: Độ ưu tiên (số cao = ưu tiên cao)
    - Active: Bật/tắt rule
    """
    
    _name = 'social.chatbot.automation'
    _description = 'Chatbot Automation Rule'
    _order = 'priority desc, sequence, id'
    _rec_name = 'name'
    
    # BASIC FIELDS
    name = fields.Char(
        string='Rule Name',
        required=True,
        help='Tên của automation rule',
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Bật/tắt rule này',
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Thứ tự hiển thị',
    )
    
    priority = fields.Integer(
        string='Priority',
        default=50,
        help='Độ ưu tiên (100 = cao nhất, 0 = thấp nhất)',
    )
    
    # TRIGGER CONFIGURATION
    trigger_keywords = fields.Char(
        string='Trigger Keywords',
        required=True,
        help='Từ khóa kích hoạt rule (phân cách bởi dấu phẩy). Ví dụ: mua,đặt hàng,order',
    )
    
    # RESPONSE CONFIGURATION
    response_text = fields.Text(
        string='Response Text',
        required=True,
        help='Nội dung tin nhắn phản hồi tự động',
    )
    
    # SCOPE
    account_id = fields.Many2one(
        'social.account',
        string='Facebook Page',
        help='Rule chỉ áp dụng cho page cụ thể (để trống = áp dụng cho tất cả)',
        ondelete='cascade',
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    
    # STATISTICS
    triggered_count = fields.Integer(
        string='Triggered Count',
        default=0,
        readonly=True,
        help='Số lần rule được kích hoạt',
    )
    
    last_triggered_date = fields.Datetime(
        string='Last Triggered',
        readonly=True,
        help='Lần cuối rule được kích hoạt',
    )
    
    # CONSTRAINTS
    @api.constrains('trigger_keywords')
    def _check_trigger_keywords(self):
        """Validate trigger keywords format"""
        for rule in self:
            if not rule.trigger_keywords:
                continue
            
            keywords = [kw.strip() for kw in rule.trigger_keywords.split(',')]
            if not keywords or all(not kw for kw in keywords):
                raise ValidationError(_(
                    'Trigger keywords must be separated by commas and not empty.\n'
                    'Example: mua,đặt hàng,order'
                ))
    
    @api.constrains('priority')
    def _check_priority(self):
        """Validate priority range"""
        for rule in self:
            if rule.priority < 0 or rule.priority > 100:
                raise ValidationError(_('Priority must be between 0 and 100'))
    
    # BUSINESS METHODS
    def mark_as_triggered(self):
        """
        Đánh dấu rule đã được kích hoạt.
        Tăng counter và cập nhật last triggered date.
        """
        self.ensure_one()
        self.write({
            'triggered_count': self.triggered_count + 1,
            'last_triggered_date': fields.Datetime.now(),
        })
        _logger.info(f"Chatbot rule '{self.name}' triggered. Total count: {self.triggered_count}")
    
    def check_match(self, message_text):
        """
        Kiểm tra xem message có match với rule hay không.
        
        Args:
            message_text (str): Nội dung tin nhắn cần kiểm tra
        
        Returns:
            bool: True nếu match, False nếu không
        """
        self.ensure_one()
        
        if not self.active:
            return False
        
        if not message_text:
            return False
        
        message_lower = message_text.lower().strip()
        keywords = [kw.strip().lower() for kw in self.trigger_keywords.split(',')]
        
        return any(keyword in message_lower for keyword in keywords if keyword)
