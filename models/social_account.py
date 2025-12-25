from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class SocialAccount(models.Model):
    _name = 'social.account'
    _description = 'Facebook Account'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Page Name', required=True, tracking=True)
    platform = fields.Selection([('facebook', 'Facebook')], string='Platform', default='facebook', required=True)
    facebook_page_id = fields.Char(string='Facebook Page ID', required=True, tracking=True)
    facebook_page_url = fields.Char(string='Page URL', compute='_compute_page_url', store=True)
    
    access_token = fields.Char(string='Access Token', required=True)
    token_expires_at = fields.Datetime(string='Token Expires At')
    is_token_valid = fields.Boolean(string='Token Valid', compute='_compute_token_valid')
    
    page_category = fields.Char(string='Category')
    page_about = fields.Text(string='About')
    followers_count = fields.Integer(string='Followers', default=0)
    likes_count = fields.Integer(string='Likes', default=0)
    page_rating = fields.Float(string='Rating', digits=(2, 1))
    profile_picture_url = fields.Char(string='Profile Picture URL')
    cover_photo_url = fields.Char(string='Cover Photo URL')
    
    active = fields.Boolean(string='Active', default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ], string='Status', default='draft', tracking=True)
    
    last_sync_date = fields.Datetime(string='Last Sync')
    last_message_sync_date = fields.Datetime(string='Last Message Sync')
    error_message = fields.Text(string='Error Message')
    
    auto_sync_comments = fields.Boolean(string='Auto Sync Comments', default=True)
    auto_sync_messages = fields.Boolean(string='Auto Sync Messages', default=True)
    
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    post_ids = fields.One2many('social.post', 'account_id', string='Posts')
    post_count = fields.Integer(string='Posts', compute='_compute_post_count')
    
    # ✅ THÊM: Field đếm conversations
    conversation_count = fields.Integer(string='Conversations', compute='_compute_conversation_count')
    
    _sql_constraints = [
        ('facebook_page_id_uniq', 'UNIQUE(facebook_page_id, company_id)', 
         'Facebook Page ID must be unique per company!'),
    ]
    
    @api.depends('facebook_page_id')
    def _compute_page_url(self):
        for account in self:
            if account.facebook_page_id:
                account.facebook_page_url = f'https://www.facebook.com/{account.facebook_page_id}'
            else:
                account.facebook_page_url = False
    
    @api.depends('token_expires_at')
    def _compute_token_valid(self):
        now = fields.Datetime.now()
        for account in self:
            if account.token_expires_at:
                account.is_token_valid = account.token_expires_at > now
            else:
                account.is_token_valid = True
    
    def _compute_post_count(self):
        for account in self:
            account.post_count = len(account.post_ids)
    
    # ✅ THÊM: Compute conversation count
    def _compute_conversation_count(self):
        for account in self:
            account.conversation_count = self.env['social.conversation'].search_count([
                ('account_id', '=', account.id)
            ])
    
    def action_test_connection(self):
        self.ensure_one()
        try:
            url = f'https://graph.facebook.com/v18.0/{self.facebook_page_id}'
            params = {'access_token': self.access_token, 'fields': 'id,name,category'}
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                self.write({'state': 'connected', 'error_message': False})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Connection successful!'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Connection failed: %s') % response.text)
        except Exception as e:
            self.write({'state': 'error', 'error_message': str(e)})
            raise UserError(_('Connection error: %s') % str(e))
    
    def action_sync_page_info(self):
        self.ensure_one()
        try:
            url = f'https://graph.facebook.com/v18.0/{self.facebook_page_id}'
            params = {
                'access_token': self.access_token,
                'fields': 'name,category,about,followers_count,fan_count,overall_star_rating'
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.write({
                    'name': data.get('name', self.name),
                    'page_category': data.get('category'),
                    'page_about': data.get('about'),
                    'followers_count': data.get('followers_count', 0),
                    'likes_count': data.get('fan_count', 0),
                    'page_rating': data.get('overall_star_rating', 0),
                    'last_sync_date': fields.Datetime.now(),
                })
                return True
            return False
        except Exception as e:
            _logger.error(f'Error syncing page info: {e}')
            return False
    
    def action_view_posts(self):
        self.ensure_one()
        return {
            'name': _('Posts - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'social.post',
            'view_mode': 'list,kanban,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }
    
    # =========================================================================
    # ✅ THÊM: ACTION SYNC CONVERSATIONS
    # =========================================================================
    def action_sync_conversations(self):
        """
        Đồng bộ tất cả conversations của account này từ Facebook.
        """
        self.ensure_one()
        
        if self.state != 'connected':
            raise UserError(_('Please connect the account first!'))
        
        try:
            from .social_message import SocialMessage
            
            # Gọi method sync cho account này
            self.env['social.message']._sync_account_conversations(self)
            
            # Cập nhật last sync date
            self.write({
                'last_message_sync_date': fields.Datetime.now(),
            })
            
            # Đếm số conversations đã sync
            conv_count = self.env['social.conversation'].search_count([
                ('account_id', '=', self.id)
            ])
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Synced conversations! Total: %d conversations') % conv_count,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f'Error syncing conversations for account {self.id}: {e}')
            raise UserError(_('Error syncing conversations: %s') % str(e))
    
    # ✅ THÊM: Action view conversations
    def action_view_conversations(self):
        """Xem tất cả conversations của account này"""
        self.ensure_one()
        return {
            'name': _('Conversations - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'social.conversation',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }
    
    @api.model
    def cron_refresh_facebook_tokens(self):
        accounts = self.search([('platform', '=', 'facebook'), ('state', '=', 'connected')])
        for account in accounts:
            try:
                _logger.info(f'Refreshing token for account {account.id}')
            except Exception as e:
                _logger.error(f'Error refreshing token: {e}')