# FILE: social_post_fixed.py
# Phiên bản sửa lỗi không thể đăng ảnh

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from datetime import datetime
import base64  # ✅ THÊM IMPORT


_logger = logging.getLogger(__name__)


class SocialPost(models.Model):
    """
    Model quản lý bài đăng Facebook.
    """
    _name = 'social.post'
    _description = 'Facebook Post'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'

    # -------------------------------------------------------------------------
    # BASIC INFO
    # -------------------------------------------------------------------------
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
    )
    
    account_id = fields.Many2one(
        'social.account',
        string='Facebook Page',
        required=True,
        domain=[('platform', '=', 'facebook')],
    )
    
    content = fields.Text(
        string='Content',
        required=True,
        tracking=True,
    )
    
    # -------------------------------------------------------------------------
    # MEDIA
    # -------------------------------------------------------------------------
    media_type = fields.Selection([
        ('text', 'Text Only'),
        ('photo', 'Photo'),
        ('video', 'Video'),
        ('link', 'Link'),
    ], string='Media Type', default='text')
    
    image = fields.Binary(string='Image', attachment=True)
    image_filename = fields.Char(string='Image Filename')
    video_url = fields.Char(string='Video URL')
    link_url = fields.Char(string='Link URL')
    
    # -------------------------------------------------------------------------
    # SCHEDULING
    # -------------------------------------------------------------------------
    post_type = fields.Selection([
        ('now', 'Publish Now'),
        ('scheduled', 'Scheduled'),
    ], string='Post Type', default='now', required=True)
    
    scheduled_date = fields.Datetime(
        string='Scheduled Date',
        tracking=True,
    )
    
    # -------------------------------------------------------------------------
    # FACEBOOK DATA
    # -------------------------------------------------------------------------
    facebook_post_id = fields.Char(
        string='Facebook Post ID',
        readonly=True,
        copy=False,
    )
    
    facebook_post_url = fields.Char(
        string='Facebook URL',
        compute='_compute_facebook_url',
        store=True,
    )
    
    published_date = fields.Datetime(
        string='Published Date',
        readonly=True,
        copy=False,
    )
    
    # -------------------------------------------------------------------------
    # STATUS
    # -------------------------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('published', 'Published'),
        ('failed', 'Failed'),
    ], string='Status', default='draft', tracking=True)
    
    error_message = fields.Text(string='Error Message')
    
    # -------------------------------------------------------------------------
    # ENGAGEMENT STATS
    # -------------------------------------------------------------------------
    likes_count = fields.Integer(string='Likes', default=0)
    comments_count = fields.Integer(string='Comments', default=0)
    shares_count = fields.Integer(string='Shares', default=0)
    reach = fields.Integer(string='Reach', default=0)
    impressions = fields.Integer(string='Impressions', default=0)
    engagement_rate = fields.Float(
        string='Engagement Rate (%)',
        compute='_compute_engagement_rate',
        store=True,
    )
    
    # -------------------------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------------------------
    comment_ids = fields.One2many(
        'social.comment',
        'post_id',
        string='Comments',
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='account_id.company_id',
        store=True,
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Created By',
        default=lambda self: self.env.user,
    )
    
    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.depends('content', 'account_id')
    def _compute_display_name(self):
        for post in self:
            if post.content:
                preview = post.content[:50] + '...' if len(post.content) > 50 else post.content
                post.display_name = f"{post.account_id.name}: {preview}"
            else:
                post.display_name = f"Post #{post.id}"
    
    @api.depends('facebook_post_id', 'account_id')
    def _compute_facebook_url(self):
        for post in self:
            if post.facebook_post_id and post.account_id:
                post.facebook_post_url = f"https://www.facebook.com/{post.facebook_post_id}"
            else:
                post.facebook_post_url = False
    
    @api.depends('likes_count', 'comments_count', 'shares_count', 'reach')
    def _compute_engagement_rate(self):
        for post in self:
            if post.reach > 0:
                total_engagement = post.likes_count + post.comments_count + post.shares_count
                post.engagement_rate = (total_engagement / post.reach) * 100
            else:
                post.engagement_rate = 0
    
    # -------------------------------------------------------------------------
    # BUSINESS METHODS
    # -------------------------------------------------------------------------
    
    def _prepare_facebook_post_data(self):
        """
        ✅ Hàm mới: Chuẩn bị dữ liệu post theo media_type
        
        Return: (url, data_dict, files_dict)
        """
        base_url = f'https://graph.facebook.com/v18.0/{self.account_id.facebook_page_id}'
        
        # Dữ liệu cơ bản
        data = {
            'access_token': self.account_id.access_token,
            'message': self.content,
        }
        
        files = None
        
        # Xử lý dựa trên media_type
        if self.media_type == 'photo':
            if not self.image:
                raise UserError(_('Please upload an image for photo post!'))
            
            # Decode base64 image
            image_binary = base64.b64decode(self.image)
            filename = self.image_filename or 'image.jpg'
            files = {'source': (filename, image_binary)}
            url = f'{base_url}/photos'
            
        elif self.media_type == 'video':
            if not self.video_url:
                raise UserError(_('Please provide a video URL!'))
            
            data['video_url'] = self.video_url
            url = f'{base_url}/feed'
            
        elif self.media_type == 'link':
            if not self.link_url:
                raise UserError(_('Please provide a link URL!'))
            
            data['link'] = self.link_url
            url = f'{base_url}/feed'
            
        else:  # text only
            url = f'{base_url}/feed'
        
        return url, data, files
    
    def action_publish_now(self):
        """✅ SỬA: Đăng bài ngay lập tức - HỖ TRỢ IMAGE"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_('Only draft posts can be published!'))
        
        try:
            # ✅ CẦU DIỆN ĐẦU TIÊN: Chuẩn bị dữ liệu
            url, data, files = self._prepare_facebook_post_data()
            
            # ✅ THAY ĐỔI: Gửi request với files nếu có image
            if files:
                # Với image: dùng multipart/form-data
                response = requests.post(url, data=data, files=files, timeout=30)
            else:
                # Chỉ text: dùng form-urlencoded thường
                response = requests.post(url, data=data, timeout=30)
            
            # Xử lý response
            if response.status_code == 200:
                result = response.json()
                self.write({
                    'facebook_post_id': result.get('id'),
                    'published_date': fields.Datetime.now(),
                    'state': 'published',
                    'error_message': False,
                })
                
                self.message_post(body=_('Post published successfully!'))
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Post published to Facebook!'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                # ✅ THÊM: Error handling tốt hơn
                try:
                    error_detail = response.json().get('error', {})
                    error_msg = error_detail.get('message', response.text)
                except:
                    error_msg = response.text
                
                raise UserError(_('Failed to publish: %s') % error_msg)
                
        except Exception as e:
            error_str = str(e)
            self.write({
                'state': 'failed',
                'error_message': error_str,
            })
            _logger.error(f'Error publishing post {self.id}: {error_str}')
            raise UserError(_('Error publishing post: %s') % error_str)
    
    def action_schedule_post(self):
        """Lên lịch đăng bài"""
        self.ensure_one()
        
        if not self.scheduled_date:
            raise UserError(_('Please set a scheduled date!'))
        
        if self.scheduled_date <= fields.Datetime.now():
            raise UserError(_('Scheduled date must be in the future!'))
        
        self.state = 'scheduled'
        self.message_post(body=_('Post scheduled for %s') % self.scheduled_date)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Post scheduled successfully!'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_sync_stats(self):
        """Đồng bộ thống kê từ Facebook"""
        self.ensure_one()
        
        if not self.facebook_post_id:
            return False
        
        try:
            url = f'https://graph.facebook.com/v18.0/{self.facebook_post_id}'
            params = {
                'access_token': self.account_id.access_token,
                'fields': 'likes.summary(true),comments.summary(true),shares'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.write({
                    'likes_count': data.get('likes', {}).get('summary', {}).get('total_count', 0),
                    'comments_count': data.get('comments', {}).get('summary', {}).get('total_count', 0),
                    'shares_count': data.get('shares', {}).get('count', 0),
                })
                return True
            else:
                _logger.error(f'Failed to sync stats: {response.text}')
                return False
                
        except Exception as e:
            _logger.error(f'Error syncing stats: {e}')
            return False
    
    def action_view_comments(self):
        """Xem comments"""
        self.ensure_one()
        return {
            'name': _('Comments'),
            'type': 'ir.actions.act_window',
            'res_model': 'social.comment',
            'view_mode': 'list,form',
            'domain': [('post_id', '=', self.id)],
            'context': {'default_post_id': self.id},
        }
    
    @api.model
    def cron_publish_scheduled_posts(self):
        """Cron job để publish scheduled posts"""
        now = fields.Datetime.now()
        posts = self.search([
            ('state', '=', 'scheduled'),
            ('scheduled_date', '<=', now),
        ])
        
        for post in posts:
            try:
                post.action_publish_now()
            except Exception as e:
                _logger.error(f'Error publishing scheduled post {post.id}: {e}')
    
    @api.model
    def cron_sync_facebook_comments(self):
        """Cron job để sync comments"""
        posts = self.search([
            ('state', '=', 'published'),
            ('facebook_post_id', '!=', False),
        ], limit=50)
        
        for post in posts:
            try:
                post.action_sync_stats()
            except Exception as e:
                _logger.error(f'Error syncing post {post.id}: {e}')
                
    def action_sync_comments(self):
        """Đồng bộ chi tiết từng comment từ Facebook về Odoo"""
        self.ensure_one()
        if not self.facebook_post_id:
            raise UserError(_('Post not published yet!'))
        
        try:
            # Gọi Graph API lấy comments
            url = f'https://graph.facebook.com/v18.0/{self.facebook_post_id}/comments'
            params = {
                'access_token': self.account_id.access_token,
                'fields': 'id,message,from,created_time,parent',
                'limit': 100
            }
            
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                
                # Loop qua từng comment
                for fb_comment in data.get('data', []):
                    # Kiểm tra xem comment đã có chưa
                    existing = self.env['social.comment'].search([
                        ('facebook_comment_id', '=', fb_comment['id']),
                        ('post_id', '=', self.id)
                    ], limit=1)
                    
                    if not existing:
                        # Tạo mới comment record
                        author = fb_comment.get('from', {})
                        self.env['social.comment'].create({
                            'post_id': self.id,
                            'facebook_comment_id': fb_comment['id'],
                            'author_name': author.get('name', 'Unknown'),
                            'author_facebook_id': author.get('id', ''),
                            'message': fb_comment.get('message', ''),
                            'comment_date': fb_comment.get('created_time'),
                            'company_id': self.company_id.id,
                        })
                
                self.message_post(body=_('Comments synced from Facebook!'))
                return True
            else:
                raise UserError(_('Failed to sync comments: %s') % response.text)
                
        except Exception as e:
            raise UserError(_('Error syncing comments: %s') % str(e))
