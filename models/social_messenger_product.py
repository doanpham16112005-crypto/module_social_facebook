# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SocialMessengerProduct(models.Model):
    """
    Sản phẩm được bán qua Facebook Messenger.
    Chỉ các sản phẩm được tick 'active' mới hiển thị trong chatbot.
    """
    _name = 'social.messenger.product'
    _description = 'Messenger Product Catalog'
    _order = 'sequence, id'
    _rec_name = 'display_name'

    # Basic Info
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        ondelete='cascade',
        domain=[('sale_ok', '=', True)],
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
    )
    active = fields.Boolean(
        string='Sell on Messenger',
        default=True,
        help='Bật để sản phẩm xuất hiện trong chatbot Messenger'
    )
    
    # Messenger Customization
    quick_reply_title = fields.Char(
        string='Quick Reply Title',
        size=20,
        help='Tiêu đề hiển thị trong quick reply button (max 20 ký tự)',
        compute='_compute_quick_reply_title',
        store=True,
        readonly=False,
    )
    description = fields.Text(
        string='Messenger Description',
        help='Mô tả gửi cho khách hàng qua Messenger',
        compute='_compute_description',
        store=True,
        readonly=False,
    )
    image_url = fields.Char(
        string='Image URL',
        compute='_compute_image_url',
        help='URL hình ảnh gửi trong Messenger (từ product.image_1920)'
    )
    
    # Pricing
    price = fields.Float(
        string='Price',
        related='product_id.list_price',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='product_id.currency_id',
        readonly=True,
    )
    
    # Organization
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Thứ tự hiển thị trong danh sách sản phẩm'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    
    # Statistics
    order_count = fields.Integer(
        string='Orders',
        compute='_compute_order_count',
    )
    
    _sql_constraints = [
        ('product_company_uniq', 
         'UNIQUE(product_id, company_id)', 
         'Product already exists in Messenger catalog for this company!'),
    ]
    
    @api.depends('product_id', 'product_id.name')
    def _compute_display_name(self):
        """Tên hiển thị = tên sản phẩm"""
        for record in self:
            record.display_name = record.product_id.name if record.product_id else ''
    
    @api.depends('product_id', 'product_id.name')
    def _compute_quick_reply_title(self):
        """Auto-fill quick reply title từ tên sản phẩm (max 20 chars)"""
        for record in self:
            if record.product_id and not record.quick_reply_title:
                name = record.product_id.name
                record.quick_reply_title = name[:20] if len(name) > 20 else name
    
    @api.depends('product_id', 'product_id.description_sale')
    def _compute_description(self):
        """Auto-fill description từ product"""
        for record in self:
            if record.product_id and not record.description:
                desc = record.product_id.description_sale or record.product_id.name
                record.description = desc
    
    @api.depends('product_id', 'product_id.image_1920')
    def _compute_image_url(self):
        """Generate public URL cho hình ảnh"""
        for record in self:
            if record.product_id and record.product_id.image_1920:
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                record.image_url = f"{base_url}/web/image/product.product/{record.product_id.id}/image_1920"
            else:
                record.image_url = False
    
    def _compute_order_count(self):
        """Đếm số đơn hàng từ sản phẩm này"""
        for record in self:
            # Count sale.order.line có product này từ messenger orders
            orders = self.env['social.messenger.order'].search([
                ('sale_order_id.order_line.product_id', '=', record.product_id.id),
                ('company_id', '=', record.company_id.id),
            ])
            record.order_count = len(orders)
    
    @api.constrains('quick_reply_title')
    def _check_quick_reply_title(self):
        """Validate quick reply title length"""
        for record in self:
            if record.quick_reply_title and len(record.quick_reply_title) > 20:
                raise ValidationError(
                    _('Quick Reply Title cannot exceed 20 characters!')
                )
    
    # -------------------------------------------------------------------------
    # BUSINESS METHODS
    # -------------------------------------------------------------------------
    
    @api.model
    def get_active_products(self, company_id=None):
        """
        Lấy danh sách sản phẩm đang active cho Messenger.
        
        Returns:
            recordset: social.messenger.product records
        """
        domain = [('active', '=', True)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        else:
            domain.append(('company_id', '=', self.env.company.id))
        
        return self.search(domain, order='sequence, id')
    
    def format_for_messenger(self):
        """
        Format sản phẩm thành quick reply buttons cho Messenger.
        
        Returns:
            list: Danh sách quick reply buttons
            [
                {
                    'content_type': 'text',
                    'title': 'Product Name',
                    'payload': 'PRODUCT_123',
                },
                ...
            ]
        """
        self.ensure_one()
        return {
            'content_type': 'text',
            'title': self.quick_reply_title or self.product_id.name[:20],
            'payload': f'PRODUCT_{self.id}',
        }
    
    def get_product_message(self):
        """
        Tạo tin nhắn giới thiệu sản phẩm.
        
        Returns:
            str: Message text
        """
        self.ensure_one()
        price_formatted = f"{self.price:,.0f} {self.currency_id.symbol}"
        message = f"🛍️ {self.product_id.name}\n"
        message += f"💰 Giá: {price_formatted}\n"
        if self.description:
            message += f"📝 {self.description}\n"
        return message
    
    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    
    def action_view_orders(self):
        """Xem các đơn hàng từ sản phẩm này"""
        self.ensure_one()
        return {
            'name': _('Messenger Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'social.messenger.order',
            'view_mode': 'tree,form',
            'domain': [
                ('sale_order_id.order_line.product_id', '=', self.product_id.id),
                ('company_id', '=', self.company_id.id),
            ],
            'context': {'default_product_id': self.product_id.id},
        }
    
    def action_toggle_active(self):
        """Toggle active state"""
        for record in self:
            record.active = not record.active