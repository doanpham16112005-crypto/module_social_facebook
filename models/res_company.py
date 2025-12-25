from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    facebook_app_id = fields.Char(
        string='Facebook App ID',
        help='Facebook App ID for authentication'
    )
    
    facebook_app_secret = fields.Char(
        string='Facebook App Secret',
        help='Facebook App Secret for authentication'
    )
    
    facebook_webhook_verify_token = fields.Char(
        string='Webhook Verify Token',
        help='Token for Facebook webhook verification'
    )
