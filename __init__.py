from . import models
from . import controllers
from . import wizard
from . import lib
import logging

_logger = logging.getLogger(__name__)

def post_init_hook(env):
    """
    Hook chạy SAU KHI module đã install xong.
    
    Dùng để tạo SQL view cho social.analytics
    vì lúc này tất cả tables đã được tạo.
    """
    import logging
    _logger = logging.getLogger(__name__)
    
    try:
        _logger.info('Running post_init_hook for module_social_facebook...')
        
        # Tạo analytics view
        env['social.analytics'].init_analytics_view()
        
        _logger.info('✅ Post init hook completed successfully')
        
    except Exception as e:
        _logger.error(f'❌ Error in post_init_hook: {e}')
        # Không raise để không block installation

def uninstall_hook(env):
    """Hook chạy trước khi gỡ cài đặt module."""
    try:
        accounts = env['social.account'].search([('platform', '=', 'facebook')])
        accounts.write({'active': False})
    except Exception as e:
        _logger.warning(f'Error during uninstall: {e}')
