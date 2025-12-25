# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import subprocess
import requests
import logging
import os

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    # -------------------------------------------------------------------------
    # FACEBOOK WEBHOOK CONFIG
    # -------------------------------------------------------------------------
    
    facebook_verify_token = fields.Char(
        string='Webhook Verify Token',
        config_parameter='module_social_facebook.verify_token',
        help='Token để verify webhook từ Facebook (GET request)',
    )
    facebook_webhook_url = fields.Char(
        string='Webhook URL',
        compute='_compute_webhook_url',
        help='URL webhook hiện tại (localhost hoặc ngrok)',
    )
    
    # -------------------------------------------------------------------------
    # NGROK CONFIG
    # -------------------------------------------------------------------------
    
    ngrok_executable_path = fields.Char(
        string='Ngrok Executable Path',
        config_parameter='module_social_facebook.ngrok_path',
        default='C:/ngrok/ngrok.exe',
        help='Đường dẫn đầy đủ tới file ngrok.exe',
    )
    ngrok_tunnel_url = fields.Char(
        string='Ngrok Public URL',
        compute='_compute_ngrok_tunnel_url',
        help='URL công khai từ ngrok (https)',
    )
    ngrok_is_running = fields.Boolean(
        string='Ngrok Running',
        compute='_compute_ngrok_is_running',
        help='Trạng thái ngrok',
    )
    
    # -------------------------------------------------------------------------
    # CRM INTEGRATION CONFIG
    # -------------------------------------------------------------------------
    
    auto_create_lead = fields.Boolean(
        string='Auto Create Leads',
        config_parameter='module_social_facebook.auto_create_lead',
        default=True,
        help='Tự động tạo crm.lead từ Messenger conversations',
    )
    lead_default_user_id = fields.Many2one(
        'res.users',
        string='Default Salesperson',
        config_parameter='module_social_facebook.lead_default_user_id',
        help='Người được assign lead mặc định',
    )
    
    # -------------------------------------------------------------------------
    # CHATBOT CONFIG
    # -------------------------------------------------------------------------
    
    chatbot_enabled = fields.Boolean(
        string='Enable Sales Chatbot',
        config_parameter='module_social_facebook.chatbot_enabled',
        default=False,
        help='Bật chatbot bán hàng tự động qua Messenger',
    )
    chatbot_welcome_message = fields.Text(
        string='Welcome Message',
        config_parameter='module_social_facebook.chatbot_welcome_message',
        default='Xin chào! Tôi là trợ lý bán hàng tự động. 😊\nBạn vui lòng cho tôi biết tên của bạn?',
        help='Tin nhắn chào mừng khi bắt đầu flow',
    )
    
    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    
    @api.depends('ngrok_tunnel_url')
    def _compute_webhook_url(self):
        """Tính toán webhook URL (ngrok hoặc localhost)"""
        for record in self:
            base_url = record.ngrok_tunnel_url or self.env['ir.config_parameter'].sudo().get_param('web.base.url', 'http://localhost:8069')
            record.facebook_webhook_url = f"{base_url}/social/facebook/webhook"
    
    def _compute_ngrok_tunnel_url(self):
        """Lấy URL ngrok từ API"""
        for record in self:
            try:
                # Query ngrok API (default: http://127.0.0.1:4040/api/tunnels)
                response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    tunnels = data.get('tunnels', [])
                    for tunnel in tunnels:
                        if tunnel.get('proto') == 'https':
                            record.ngrok_tunnel_url = tunnel.get('public_url')
                            return
                record.ngrok_tunnel_url = False
            except Exception as e:
                _logger.debug(f'Failed to get ngrok URL: {e}')
                record.ngrok_tunnel_url = False
    
    def _compute_ngrok_is_running(self):
        """Kiểm tra ngrok có đang chạy không"""
        for record in self:
            record.ngrok_is_running = bool(record.ngrok_tunnel_url)
    
    # -------------------------------------------------------------------------
    # NGROK ACTIONS
    # -------------------------------------------------------------------------
    
    def action_start_ngrok(self):
        """
        Khởi động ngrok subprocess.
        
        Command: ngrok.exe http 8069
        Process chạy background, không block Odoo.
        """
        self.ensure_one()
        
        ngrok_path = self.ngrok_executable_path or 'C:/ngrok/ngrok.exe'
        
        # Check if file exists
        if not os.path.exists(ngrok_path):
            raise UserError(_(
                'Ngrok executable not found at: %s\n'
                'Please update the path in settings!'
            ) % ngrok_path)
        
        # Check if already running
        if self.ngrok_is_running:
            raise UserError(_('Ngrok is already running!'))
        
        try:
            # Start ngrok subprocess
            # Use Popen to run in background
            subprocess.Popen(
                [ngrok_path, 'http', '8069'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            )
            
            _logger.info('Ngrok started successfully')
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Ngrok started! Please wait 5 seconds then refresh to see the URL.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f'Failed to start ngrok: {e}')
            raise UserError(_(
                'Failed to start ngrok: %s\n'
                'Please check the executable path and try again.'
            ) % str(e))
    
    def action_stop_ngrok(self):
        """
        Dừng ngrok process.
        
        Kill tất cả process ngrok đang chạy.
        """
        self.ensure_one()
        
        try:
            if os.name == 'nt':  # Windows
                subprocess.run(['taskkill', '/F', '/IM', 'ngrok.exe'], 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
            else:  # Linux/Mac
                subprocess.run(['pkill', 'ngrok'], 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
            
            _logger.info('Ngrok stopped')
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Ngrok stopped successfully!'),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f'Failed to stop ngrok: {e}')
            raise UserError(_('Failed to stop ngrok: %s') % str(e))
    
    def action_refresh_ngrok_url(self):
        """Refresh để lấy ngrok URL mới"""
        self._compute_ngrok_tunnel_url()
        
        if self.ngrok_tunnel_url:
            message = _('Ngrok URL: %s') % self.ngrok_tunnel_url
            msg_type = 'success'
        else:
            message = _('Ngrok is not running or URL not available.')
            msg_type = 'warning'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Ngrok Status'),
                'message': message,
                'type': msg_type,
                'sticky': False,
            }
        }
    
    def action_copy_webhook_url(self):
        """Copy webhook URL to clipboard (via notification)"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Webhook URL'),
                'message': _('Webhook URL: %s\nCopy và dán vào Facebook App Settings!') % self.facebook_webhook_url,
                'type': 'info',
                'sticky': True,
            }
        }
    