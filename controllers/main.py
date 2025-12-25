from odoo import http
from odoo.http import request


class SocialFacebookController(http.Controller):
    """
    Controller chính cho Facebook integration.
    """

    @http.route('/social/facebook/oauth/callback', type='http', auth='user', website=True)
    def facebook_oauth_callback(self, **kwargs):
        """
        Callback URL sau khi user authorize Facebook app.
        """
        code = kwargs.get('code')
        state = kwargs.get('state')
        
        if not code:
            return request.render('module_social_facebook.oauth_error', {
                'error': 'No authorization code received'
            })
        
        # Process OAuth code and exchange for access token
        # Logic xử lý ở đây
        
        return request.redirect('/web#action=module_social_facebook.action_social_account')
