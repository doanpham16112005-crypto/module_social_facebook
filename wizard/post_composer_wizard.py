from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class PostComposerWizard(models.TransientModel):
    """
    Wizard để tạo và đăng bài nhanh lên Facebook.
    Cho phép publish ngay hoặc lên lịch.
    """
    _name = 'social.post.composer.wizard'
    _description = 'Quick Post Composer Wizard'

    # -------------------------------------------------------------------------
    # BASIC FIELDS
    # -------------------------------------------------------------------------
    account_ids = fields.Many2many(
        'social.account',
        string='Facebook Pages',
        required=True,
        domain=[('platform', '=', 'facebook'), ('state', '=', 'connected')],
        help='Select which pages to post to'
    )
    
    content = fields.Text(
        string='Post Content',
        required=True,
        help='What do you want to share?'
    )
    
    template_id = fields.Many2one(
        'social.post.template',
        string='Use Template',
        help='Select a template to start with'
    )
    
    # -------------------------------------------------------------------------
    # MEDIA
    # -------------------------------------------------------------------------
    media_type = fields.Selection([
        ('text', 'Text Only'),
        ('photo', 'Photo'),
        ('link', 'Link'),
    ], string='Post Type', default='text', required=True)
    
    image = fields.Binary(
        string='Image',
        attachment=True,
    )
    
    image_filename = fields.Char(string='Image Filename')
    
    link_url = fields.Char(
        string='Link URL',
        help='Share a link (optional)'
    )
    
    # -------------------------------------------------------------------------
    # SCHEDULING
    # -------------------------------------------------------------------------
    post_method = fields.Selection([
        ('now', 'Publish Now'),
        ('scheduled', 'Schedule for Later'),
    ], string='When to Post', default='now', required=True)
    
    scheduled_date = fields.Datetime(
        string='Schedule Date',
        help='When should this post be published?'
    )
    
    # -------------------------------------------------------------------------
    # PREVIEW
    # -------------------------------------------------------------------------
    preview_text = fields.Html(
        string='Preview',
        compute='_compute_preview_text',
        sanitize=False,
    )
    
    character_count = fields.Integer(
        string='Characters',
        compute='_compute_character_count',
    )
    
    # -------------------------------------------------------------------------
    # STATS
    # -------------------------------------------------------------------------
    page_count = fields.Integer(
        string='Number of Pages',
        compute='_compute_page_count',
    )
    
    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Load template content"""
        if self.template_id:
            self.content = self.template_id.content
    
    @api.depends('content')
    def _compute_character_count(self):
        """Count characters in content"""
        for wizard in self:
            wizard.character_count = len(wizard.content or '')
    
    @api.depends('account_ids')
    def _compute_page_count(self):
        """Count selected pages"""
        for wizard in self:
            wizard.page_count = len(wizard.account_ids)
    
    @api.depends('content', 'link_url', 'media_type')
    def _compute_preview_text(self):
        """Generate preview of the post"""
        for wizard in self:
            preview = '<div style="border: 1px solid #e0e0e0; padding: 15px; border-radius: 8px; background-color: #f9f9f9;">'
            preview += '<div style="margin-bottom: 10px;">'
            preview += '<i class="fa fa-facebook-square" style="color: #1877f2; font-size: 20px;"></i> '
            preview += '<strong>Facebook Post Preview</strong>'
            preview += '</div>'
            
            if wizard.content:
                preview += f'<p style="white-space: pre-wrap; margin-bottom: 10px;">{wizard.content}</p>'
            
            if wizard.link_url:
                preview += f'<div style="border: 1px solid #ddd; padding: 10px; border-radius: 5px; background-color: #fff;">'
                preview += f'<i class="fa fa-link"></i> <a href="{wizard.link_url}" target="_blank">{wizard.link_url}</a>'
                preview += '</div>'
            
            if wizard.media_type == 'photo':
                preview += '<div style="margin-top: 10px;">'
                preview += '<i class="fa fa-camera"></i> <em>Image will be attached</em>'
                preview += '</div>'
            
            preview += '</div>'
            wizard.preview_text = preview
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    @api.constrains('scheduled_date', 'post_method')
    def _check_scheduled_date(self):
        """Validate scheduled date"""
        for wizard in self:
            if wizard.post_method == 'scheduled':
                if not wizard.scheduled_date:
                    raise ValidationError(_('Please set a scheduled date!'))
                if wizard.scheduled_date <= fields.Datetime.now():
                    raise ValidationError(_('Scheduled date must be in the future!'))
    
    @api.constrains('content')
    def _check_content_length(self):
        """Check content length"""
        for wizard in self:
            if wizard.content and len(wizard.content) > 63206:
                raise ValidationError(_('Facebook posts are limited to 63,206 characters!'))
    
    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    def action_publish(self):
        """Create and publish/schedule posts"""
        self.ensure_one()
        
        if not self.account_ids:
            raise UserError(_('Please select at least one Facebook Page!'))
        
        created_posts = self.env['social.post']
        
        for account in self.account_ids:
            post_vals = {
                'account_id': account.id,
                'content': self.content,
                'media_type': self.media_type,
                'link_url': self.link_url,
                'post_type': self.post_method,
            }
            
            if self.media_type == 'photo' and self.image:
                post_vals.update({
                    'image': self.image,
                    'image_filename': self.image_filename,
                })
            
            if self.post_method == 'scheduled':
                post_vals['scheduled_date'] = self.scheduled_date
            
            post = self.env['social.post'].create(post_vals)
            created_posts |= post
            
            # If publish now, trigger publish action
            if self.post_method == 'now':
                try:
                    post.action_publish_now()
                except Exception as e:
                    _logger.error(f'Error publishing post {post.id}: {e}')
                    raise UserError(_('Error publishing to %s: %s') % (account.name, str(e)))
            else:
                post.state = 'scheduled'
        
        # Show success notification
        message = _('Successfully created %d post(s)!') % len(created_posts)
        if self.post_method == 'now':
            message = _('Successfully published to %d page(s)!') % len(self.account_ids)
        else:
            message = _('Successfully scheduled %d post(s) for %s') % (
                len(created_posts), 
                self.scheduled_date.strftime('%Y-%m-%d %H:%M')
            )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'social.post',
                    'view_mode': 'list,form',
                    'domain': [('id', 'in', created_posts.ids)],
                }
            }
        }
    
    def action_preview(self):
        """Show preview of the post"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Post Preview'),
            'res_model': 'social.post.composer.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
