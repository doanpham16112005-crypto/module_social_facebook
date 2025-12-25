# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SocialMessengerOrder(models.Model):
    """
    Đơn hàng được tạo từ Facebook Messenger.
    Link với sale.order và social.conversation.
    """
    _name = 'social.messenger.order'
    _description = 'Messenger Sales Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'order_date desc, id desc'
    _rec_name = 'name'

    # Basic Info
    name = fields.Char(
        string='Order Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        ondelete='cascade',
        tracking=True,
    )
    conversation_id = fields.Many2one(
        'social.message',  # Link tới conversation
        string='Conversation',
        ondelete='set null',
        help='Cuộc hội thoại Messenger tạo ra đơn hàng này',
    )
    
    # Customer Info
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='sale_order_id.partner_id',
        store=True,
        readonly=True,
    )
    facebook_user_id = fields.Char(
        string='Facebook User ID',
        help='PSID của khách hàng',
        tracking=True,
    )
    customer_name = fields.Char(
        string='Customer Name',
        required=True,
        tracking=True,
    )
    customer_phone = fields.Char(
        string='Phone',
        required=True,
        tracking=True,
    )
    customer_email = fields.Char(
        string='Email',
        tracking=True,
    )
    
    # Order Details
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('sale', 'Sale Order'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    order_date = fields.Datetime(
        string='Order Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    
    # Products
    product_ids = fields.Many2many(
        'social.messenger.product',
        string='Products',
        help='Sản phẩm khách hàng đã chọn',
    )
    
    # Pricing
    total_amount = fields.Monetary(
        string='Total',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    
    # Organization
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Salesperson',
        default=lambda self: self.env.user,
        tracking=True,
    )
    
    # Notes
    notes = fields.Text(
        string='Internal Notes',
    )
    
    @api.model
    def create(self, vals):
        """Override create để tạo sequence"""
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'social.messenger.order'
            ) or _('New')
        return super().create(vals)
    
    @api.depends('sale_order_id', 'sale_order_id.amount_total')
    def _compute_total_amount(self):
        """Tính tổng tiền từ sale.order hoặc products"""
        for record in self:
            if record.sale_order_id:
                record.total_amount = record.sale_order_id.amount_total
            else:
                # Tính tổng từ products
                total = sum(record.product_ids.mapped('price'))
                record.total_amount = total
    
    # -------------------------------------------------------------------------
    # BUSINESS METHODS
    # -------------------------------------------------------------------------
    
    def create_sale_order(self):
        """
        Tạo sale.order từ messenger order.
        
        Flow:
        1. Tìm hoặc tạo res.partner
        2. Tạo sale.order
        3. Thêm order lines từ products
        4. Link sale_order_id
        5. Chuyển state → 'sale'
        """
        self.ensure_one()
        
        if self.sale_order_id:
            raise UserError(_('Sale Order already exists for this Messenger Order!'))
        
        if not self.product_ids:
            raise UserError(_('Please select at least one product!'))
        
        # 1. Find or create partner
        partner = self._find_or_create_partner()
        
        # 2. Create sale.order
        sale_vals = {
            'partner_id': partner.id,
            'user_id': self.user_id.id,
            'company_id': self.company_id.id,
            'date_order': self.order_date,
            'origin': f'Messenger: {self.name}',
            'note': self.notes or f'Order from Facebook Messenger\nFacebook User: {self.facebook_user_id}',
        }
        
        sale_order = self.env['sale.order'].create(sale_vals)
        
        # 3. Add order lines
        for product in self.product_ids:
            line_vals = {
                'order_id': sale_order.id,
                'product_id': product.product_id.id,
                'product_uom_qty': 1,  # Default quantity
                'price_unit': product.price,
            }
            self.env['sale.order.line'].create(line_vals)
        
        # 4. Link sale order
        self.sale_order_id = sale_order.id
        self.state = 'sale'
        
        # 5. Send confirmation message
        self.send_order_confirmation()
        
        # 6. Log activity
        self.message_post(
            body=_('Sale Order %s created from Messenger') % sale_order.name,
            subject=_('Sale Order Created'),
        )
        
        return sale_order
    
    def _find_or_create_partner(self):
        """
        Tìm hoặc tạo res.partner từ thông tin khách hàng.
        
        Logic:
        - Tìm theo facebook_user_id (custom field)
        - Nếu không có, tìm theo phone
        - Nếu không có, tạo mới
        
        Returns:
            res.partner: Partner record
        """
        Partner = self.env['res.partner']
        
        # Check if partner has facebook_user_id field (custom field)
        if 'facebook_user_id' in Partner._fields:
            partner = Partner.search([
                ('facebook_user_id', '=', self.facebook_user_id),
                ('company_id', 'in', [False, self.company_id.id]),
            ], limit=1)
            if partner:
                return partner
        
        # Search by phone
        if self.customer_phone:
            partner = Partner.search([
                ('phone', '=', self.customer_phone),
                ('company_id', 'in', [False, self.company_id.id]),
            ], limit=1)
            if partner:
                # Update facebook_user_id if field exists
                if 'facebook_user_id' in Partner._fields and not partner.facebook_user_id:
                    partner.facebook_user_id = self.facebook_user_id
                return partner
        
        # Create new partner
        partner_vals = {
            'name': self.customer_name,
            'phone': self.customer_phone,
            'email': self.customer_email,
            'company_id': self.company_id.id,
            'comment': f'Created from Facebook Messenger Order: {self.name}',
        }
        
        # Add facebook_user_id if field exists
        if 'facebook_user_id' in Partner._fields:
            partner_vals['facebook_user_id'] = self.facebook_user_id
        
        partner = Partner.create(partner_vals)
        
        _logger.info(f'Created new partner {partner.id} for Messenger Order {self.name}')
        
        return partner
    
    def send_order_confirmation(self):
        """
        Gửi tin nhắn xác nhận đơn hàng qua Messenger.
        
        Message format:
        ✅ Đơn hàng #{name} đã được xác nhận!
        📦 Sản phẩm: [Product List]
        💰 Tổng tiền: {total}
        📞 Chúng tôi sẽ liên hệ bạn sớm!
        """
        self.ensure_one()
        
        if not self.conversation_id:
            _logger.warning(f'No conversation found for order {self.name}')
            return
        
        # Build message
        product_list = '\n'.join([
            f"  • {p.product_id.name} - {p.price:,.0f} {p.currency_id.symbol}"
            for p in self.product_ids
        ])
        
        message = f"""✅ Đơn hàng #{self.name} đã được xác nhận!

📦 Sản phẩm:
{product_list}

💰 Tổng tiền: {self.total_amount:,.0f} {self.currency_id.symbol}

📞 Chúng tôi sẽ liên hệ với bạn trong thời gian sớm nhất!
Cảm ơn bạn đã mua hàng."""
        
        # Send via Messenger API
        try:
            # Get Facebook API wrapper
            from odoo.addons.module_social_facebook.lib import facebook_api
            
            # Get page access token from conversation's account
            account = self.conversation_id.account_id
            if not account or not account.access_token:
                _logger.error(f'No access token found for conversation {self.conversation_id.id}')
                return
            
            api = facebook_api.FacebookAPI(account.access_token)
            
            # Send message
            api.send_message(
                recipient_id=self.facebook_user_id,
                message={'text': message}
            )
            
            _logger.info(f'Sent order confirmation for {self.name} to {self.facebook_user_id}')
            
            # Log to chatter
            self.message_post(
                body=_('Order confirmation sent via Messenger'),
                subject=_('Confirmation Sent'),
            )
            
        except Exception as e:
            _logger.error(f'Failed to send confirmation for order {self.name}: {e}')
            self.message_post(
                body=_('Failed to send confirmation: %s') % str(e),
                subject=_('Error'),
            )
    
    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    
    def action_confirm(self):
        """Xác nhận đơn hàng"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft orders can be confirmed!'))
            record.state = 'confirmed'
            record.message_post(body=_('Order confirmed'))
    
    def action_create_sale_order(self):
        """Button action: Tạo sale.order"""
        self.ensure_one()
        sale_order = self.create_sale_order()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_sale_order(self):
        """Xem sale.order"""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_('No Sale Order linked yet!'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_cancel(self):
        """Hủy đơn hàng"""
        for record in self:
            record.state = 'cancelled'
            record.message_post(body=_('Order cancelled'))


# -------------------------------------------------------------------------
# EXTEND res.partner (OPTIONAL)
# -------------------------------------------------------------------------
# Thêm field facebook_user_id vào res.partner để tracking

class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    facebook_user_id = fields.Char(
        string='Facebook User ID (PSID)',
        help='Facebook Page-Scoped User ID',
    )
    messenger_order_count = fields.Integer(
        string='Messenger Orders',
        compute='_compute_messenger_order_count',
    )
    
    def _compute_messenger_order_count(self):
        """Đếm số đơn hàng Messenger"""
        for partner in self:
            partner.messenger_order_count = self.env['social.messenger.order'].search_count([
                ('partner_id', '=', partner.id)
            ])
    
    def action_view_messenger_orders(self):
        """Xem đơn hàng Messenger"""
        self.ensure_one()
        return {
            'name': _('Messenger Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'social.messenger.order',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
        }