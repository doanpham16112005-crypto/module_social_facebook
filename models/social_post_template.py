from odoo import models, fields, api, _


class SocialPostTemplate(models.Model):
    """
    Model quản lý templates cho bài đăng.
    """
    _name = 'social.post.template'
    _description = 'Social Post Template'
    _order = 'name'

    name = fields.Char(
        string='Template Name',
        required=True,
    )
    
    template_type = fields.Selection([
        ('product_launch', 'Product Launch'),
        ('promotion', 'Promotion'),
        ('testimonial', 'Testimonial'),
        ('educational', 'Educational'),
        ('engagement', 'Engagement'),
        ('event', 'Event'),
        ('custom', 'Custom'),
    ], string='Type', default='custom')
    
    content = fields.Text(
        string='Content Template',
        required=True,
        help='Use {{variable_name}} for dynamic content'
    )
    
    description = fields.Text(string='Description')
    
    active = fields.Boolean(string='Active', default=True)
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    
    def action_use_template(self):
        """Sử dụng template để tạo post mới"""
        self.ensure_one()
        return {
            'name': _('New Post from Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'social.post',
            'view_mode': 'form',
            'context': {
                'default_content': self.content,
            },
        }