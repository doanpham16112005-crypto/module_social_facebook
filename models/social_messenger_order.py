# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SocialMessengerOrder(models.Model):
    """
    ✅ VERSION ĐƠN GIẢN - KHÔNG GỌI send_order_confirmation() trong create_sale_order()
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
        'social.message',
        string='Conversation',
        ondelete='set null',
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
        """Tính tổng tiền"""
        for record in self:
            if record.sale_order_id:
                record.total_amount = record.sale_order_id.amount_total
            else:
                total = sum(record.product_ids.mapped('price'))
                record.total_amount = total
    
    def create_sale_order(self):
        """
        ✅ TẠO SALE ORDER - KHÔNG GỌI send_order_confirmation()
        
        Webhook sẽ tự gửi tin nhắn confirmation.
        """
        self.ensure_one()
        
        if self.sale_order_id:
            raise UserError(_('Sale Order already exists!'))
        
        if not self.product_ids:
            raise UserError(_('No products selected!'))
        
        # 1. Find or create partner
        partner = self._find_or_create_partner()
        
        # 2. Create sale.order
        sale_vals = {
            'partner_id': partner.id,
            'user_id': self.user_id.id,
            'company_id': self.company_id.id,
            'date_order': self.order_date,
            'origin': f'Messenger: {self.name}',
            'note': f'Order from Facebook Messenger\nPSID: {self.facebook_user_id}',
        }
        
        sale_order = self.env['sale.order'].create(sale_vals)
        
        # 3. Add order lines
        for product in self.product_ids:
            line_vals = {
                'order_id': sale_order.id,
                'product_id': product.product_id.id,
                'product_uom_qty': 1,
                'price_unit': product.price,
            }
            self.env['sale.order.line'].create(line_vals)
        
        # 4. Link sale order
        self.sale_order_id = sale_order.id
        self.state = 'sale'
        
        # ✅ KHÔNG GỌI send_order_confirmation() - Webhook tự gửi
        
        # 5. Log activity
        self.message_post(
            body=_('Sale Order %s created from Messenger') % sale_order.name,
            subject=_('Sale Order Created'),
        )
        
        _logger.info(f'✅ Created sale order {sale_order.name} for {self.name}')
        
        return sale_order
    
    def _find_or_create_partner(self):
        """Tìm hoặc tạo res.partner"""
        Partner = self.env['res.partner']
        
        # Search by phone
        if self.customer_phone:
            partner = Partner.search([
                ('phone', '=', self.customer_phone),
                ('company_id', 'in', [False, self.company_id.id]),
            ], limit=1)
            if partner:
                return partner
        
        # Create new partner
        partner_vals = {
            'name': self.customer_name,
            'phone': self.customer_phone,
            'email': self.customer_email,
            'company_id': self.company_id.id,
            'comment': f'Created from Messenger Order: {self.name}',
        }
        
        partner = Partner.create(partner_vals)
        
        _logger.info(f'Created partner {partner.id} for order {self.name}')
        
        return partner
    
    # ✅ XÓA METHOD send_order_confirmation() - Webhook tự xử lý
    
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


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    facebook_user_id = fields.Char(
        string='Facebook User ID (PSID)',
    )
    messenger_order_count = fields.Integer(
        string='Messenger Orders',
        compute='_compute_messenger_order_count',
    )
    
    def _compute_messenger_order_count(self):
        for partner in self:
            partner.messenger_order_count = self.env['social.messenger.order'].search_count([
                ('partner_id', '=', partner.id)
            ])
    
    def action_view_messenger_orders(self):
        self.ensure_one()
        return {
            'name': _('Messenger Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'social.messenger.order',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
        }