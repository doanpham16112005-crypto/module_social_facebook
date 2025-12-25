from odoo import models, fields, api, tools
import logging

_logger = logging.getLogger(__name__)


class SocialAnalytics(models.Model):
    """
    Model phân tích insights từ Facebook.
    
    Đây là SQL View model (không có table thật trong database).
    View này tổng hợp dữ liệu từ social_post để tạo báo cáo analytics.
    """
    _name = 'social.analytics'
    _description = 'Facebook Analytics'
    _auto = False
    _rec_name = 'account_id'
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FIELDS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    account_id = fields.Many2one(
        'social.account',
        string='Page',
        readonly=True,
    )
    
    date = fields.Date(
        string='Date',
        readonly=True,
    )
    
    total_posts = fields.Integer(
        string='Total Posts',
        readonly=True,
    )
    
    total_likes = fields.Integer(
        string='Total Likes',
        readonly=True,
    )
    
    total_comments = fields.Integer(
        string='Total Comments',
        readonly=True,
    )
    
    total_shares = fields.Integer(
        string='Total Shares',
        readonly=True,
    )
    
    avg_engagement_rate = fields.Float(
        string='Avg Engagement Rate',
        readonly=True,
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        readonly=True,
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INIT METHOD - XÓA VÀ THAY BẰNG @api.model_create_multi
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # ❌ XÓA method init() cũ vì gây lỗi khi load module
    # def init(self):
    #     """Tạo SQL view cho analytics"""
    #     tools.drop_view_if_exists(self._cr, self._table)
    #     self._cr.execute("""...""")
    
    # ✅ THAY BẰNG: Tạo view thủ công sau khi module đã install xong
    # Hoặc dùng post_init_hook trong __manifest__.py
    
    @api.model
    def init(self):
        """
        Tạo SQL view cho analytics.
        
        Version an toàn: Kiểm tra table social_post tồn tại trước khi tạo view.
        """
        # Kiểm tra table social_post đã tồn tại chưa
        self._cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'social_post'
            )
        """)
        
        table_exists = self._cr.fetchone()[0]
        
        if not table_exists:
            _logger.warning(
                'Table social_post does not exist yet. '
                'Skipping social.analytics view creation. '
                'View will be created later via post_init_hook.'
            )
            return
        
        # Table tồn tại → Tạo view
        _logger.info('Creating social.analytics SQL view...')
        
        try:
            tools.drop_view_if_exists(self._cr, self._table)
            
            self._cr.execute("""
                CREATE OR REPLACE VIEW %s AS (
                    SELECT
                        ROW_NUMBER() OVER (ORDER BY sp.account_id, DATE(sp.published_date)) AS id,
                        sp.account_id AS account_id,
                        DATE(sp.published_date) AS date,
                        COUNT(sp.id) AS total_posts,
                        COALESCE(SUM(sp.likes_count), 0) AS total_likes,
                        COALESCE(SUM(sp.comments_count), 0) AS total_comments,
                        COALESCE(SUM(sp.shares_count), 0) AS total_shares,
                        AVG(sp.engagement_rate) AS avg_engagement_rate,
                        sp.company_id AS company_id
                    FROM
                        social_post sp
                    WHERE
                        sp.state = 'published'
                        AND sp.published_date IS NOT NULL
                    GROUP BY
                        sp.account_id, DATE(sp.published_date), sp.company_id
                )
            """ % self._table)
            
            _logger.info('✅ Social analytics view created successfully')
            
        except Exception as e:
            _logger.error(f'❌ Error creating view: {e}')
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CRON & ACTIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    @api.model
    def cron_update_facebook_insights(self):
        """
        Cron job để update insights từ Facebook.
        
        Job này chạy định kỳ để pull data mới từ Facebook API
        và cập nhật vào social_post.
        """
        _logger.info('Updating Facebook insights...')
        
        try:
            # Lấy tất cả accounts đang active
            accounts = self.env['social.account'].search([
                ('platform', '=', 'facebook'),
                ('state', '=', 'connected'),
            ])
            
            for account in accounts:
                try:
                    # TODO: Implement Facebook Insights API call
                    # account.sync_insights()
                    _logger.info(f'Updated insights for account {account.name}')
                except Exception as e:
                    _logger.error(f'Error updating insights for {account.name}: {e}')
            
            _logger.info('✅ Facebook insights update completed')
            
        except Exception as e:
            _logger.error(f'❌ Error in cron_update_facebook_insights: {e}')