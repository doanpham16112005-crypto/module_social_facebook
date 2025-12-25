# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
import re

_logger = logging.getLogger(__name__)


class SocialMessage(models.Model):
    """
    Model quản lý Facebook Messenger conversations và messages.
    
    Model này đại diện cho:
    1. Conversations: Cuộc hội thoại với một user (identified by PSID)
    2. Messages: Tin nhắn riêng lẻ trong conversation
    
    Chatbot Flow:
    - idle → ask_name → ask_phone → show_products → confirm_order → completed
    
    Integration:
    - CRM: Auto-create crm.lead từ conversations
    - Sales: Create sale.order từ chatbot
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MODEL DEFINITION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _name = 'social.message'
    _description = 'Social Message / Conversation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'facebook_user_id'
    
    # THÊM field này vào phần khai báo fields:
    conversation_id = fields.Many2one(
        'social.conversation',
        string='Conversation',
        ondelete='cascade',
        help='Conversation mà message này thuộc về'
    )
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BASIC CONVERSATION FIELDS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Conversation Identification
    facebook_user_id = fields.Char(
        string='Facebook User ID (PSID)',
        required=True,
        index=True,
        help='Page-Scoped User ID from Facebook',
    )
    account_id = fields.Many2one(
        'social.account',
        string='Facebook Page',
        required=True,
        ondelete='cascade',
        index=True,
        help='Facebook Page nhận tin nhắn',
    )
    
    # Message Details
    message_id = fields.Char(
        string='Message ID',
        index=True,
        help='Facebook Message ID (unique cho mỗi message)',
    )
    message = fields.Text(
        string='Message Content',
        help='Nội dung tin nhắn',
    )
    is_from_customer = fields.Boolean(
        string='From Customer',
        default=True,
        help='True = từ khách hàng, False = từ Page',
    )
    attachments = fields.Text(
        string='Attachments',
        help='JSON data của file đính kèm (images, files, etc.)',
    )
    
    # Timestamps
    created_date = fields.Datetime(
        string='Created Date',
        default=fields.Datetime.now,
        index=True,
    )
    last_message_date = fields.Datetime(
        string='Last Message',
        help='Thời điểm tin nhắn cuối cùng',
    )
    
    # Organization
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CHATBOT FIELDS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    chatbot_state = fields.Selection([
        ('idle', 'Idle'),
        ('ask_name', 'Asking Name'),
        ('ask_phone', 'Asking Phone'),
        ('show_products', 'Showing Products'),
        ('confirm_order', 'Confirming Order'),
        ('completed', 'Completed'),
    ], string='Chatbot State', default='idle', tracking=True)
    
    customer_name = fields.Char(
        string='Customer Name',
        help='Tên khách hàng trong cuộc hội thoại',
    )
    customer_phone = fields.Char(
        string='Customer Phone',
        help='Số điện thoại khách hàng',
    )
    selected_product_ids = fields.Many2many(
        'social.messenger.product',
        string='Selected Products',
        help='Sản phẩm khách hàng đã chọn',
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CRM & SALES INTEGRATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        ondelete='set null',
        help='Lead được tạo từ conversation này',
    )
    messenger_order_id = fields.Many2one(
        'social.messenger.order',
        string='Messenger Order',
        ondelete='set null',
        help='Đơn hàng được tạo từ conversation này',
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONSTRAINTS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    _sql_constraints = [
        ('facebook_user_account_uniq',
         'UNIQUE(facebook_user_id, account_id)',
         'Conversation already exists for this user and page!'),
    ]
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CHATBOT FLOW METHODS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def process_chatbot_flow(self, user_message):
        """
        Xử lý luồng hội thoại chatbot bán hàng.
        
        Flow:
        1. idle → ask_name: Chào hỏi, xin tên
        2. ask_name → ask_phone: Lưu tên, xin SĐT
        3. ask_phone → show_products: Lưu SĐT, show danh sách SP
        4. show_products → confirm_order: Lưu SP đã chọn
        5. confirm_order → completed: Tạo đơn hàng
        
        Args:
            user_message (str): Tin nhắn của user
        
        Returns:
            dict: Response message to send
        """
        self.ensure_one()
        
        # Check if chatbot is enabled
        chatbot_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        if chatbot_enabled != 'True':
            return None
        
        current_state = self.chatbot_state
        
        if current_state == 'idle':
            return self._chatbot_ask_name()
        
        elif current_state == 'ask_name':
            return self._chatbot_save_name_ask_phone(user_message)
        
        elif current_state == 'ask_phone':
            return self._chatbot_save_phone_show_products(user_message)
        
        elif current_state == 'show_products':
            return self._chatbot_save_product_selection(user_message)
        
        elif current_state == 'confirm_order':
            return self._chatbot_create_order(user_message)
        
        return None
    
    def _chatbot_ask_name(self):
        """State 1: Hỏi tên khách hàng"""
        self.chatbot_state = 'ask_name'
        
        welcome_msg = self.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_welcome_message',
            'Xin chào! Tôi là trợ lý bán hàng tự động. 😊\nBạn vui lòng cho tôi biết tên của bạn?'
        )
        
        return {
            'text': welcome_msg
        }
    
    def _chatbot_save_name_ask_phone(self, user_message):
        """State 2: Lưu tên, hỏi SĐT"""
        # Extract name from message
        name = user_message.strip()
        if len(name) < 2:
            return {
                'text': 'Tên bạn có vẻ hơi ngắn. Bạn vui lòng nhập lại tên đầy đủ nhé! 😊'
            }
        
        self.customer_name = name
        self.chatbot_state = 'ask_phone'
        
        return {
            'text': f'Rất vui được làm quen với {name}! 👋\n\nĐể chúng tôi có thể liên hệ xác nhận đơn hàng, bạn vui lòng cung cấp số điện thoại?'
        }
    
    def _chatbot_save_phone_show_products(self, user_message):
        """State 3: Lưu SĐT, hiển thị sản phẩm"""
        # Validate phone number (simple regex)
        phone = user_message.strip()
        phone_pattern = r'^[0-9\s\+\-\(\)]{9,15}$'
        
        if not re.match(phone_pattern, phone):
            return {
                'text': 'Số điện thoại có vẻ không hợp lệ. Vui lòng nhập lại số điện thoại của bạn (10-11 số).'
            }
        
        self.customer_phone = phone
        self.chatbot_state = 'show_products'
        
        # Get active products
        products = self.env['social.messenger.product'].get_active_products(
            company_id=self.company_id.id
        )
        
        if not products:
            return {
                'text': 'Xin lỗi, hiện tại chúng tôi chưa có sản phẩm nào. Vui lòng quay lại sau! 😊'
            }
        
        # Create quick replies for products
        quick_replies = []
        product_list = "📦 Danh sách sản phẩm:\n\n"
        
        for idx, product in enumerate(products, 1):
            product_list += f"{idx}. {product.product_id.name}\n"
            product_list += f"   💰 {product.price:,.0f} {product.currency_id.symbol}\n"
            if product.description:
                product_list += f"   📝 {product.description[:50]}...\n"
            product_list += "\n"
            
            quick_replies.append(product.format_for_messenger())
        
        product_list += "Vui lòng chọn sản phẩm bạn muốn mua:"
        
        return {
            'text': product_list,
            'quick_replies': quick_replies
        }
    
    def _chatbot_save_product_selection(self, user_message):
        """State 4: Lưu sản phẩm đã chọn, xác nhận"""
        # Parse product ID from payload (format: PRODUCT_123)
        if user_message.startswith('PRODUCT_'):
            try:
                product_id = int(user_message.replace('PRODUCT_', ''))
                product = self.env['social.messenger.product'].browse(product_id)
                
                if not product.exists() or not product.active:
                    return {
                        'text': 'Sản phẩm không tồn tại hoặc đã hết hàng. Vui lòng chọn sản phẩm khác.'
                    }
                
                # Add to selected products
                self.selected_product_ids = [(4, product.id)]
                self.chatbot_state = 'confirm_order'
                
                # Build confirmation message
                total = sum(self.selected_product_ids.mapped('price'))
                product_list = '\n'.join([
                    f"  • {p.product_id.name} - {p.price:,.0f} {p.currency_id.symbol}"
                    for p in self.selected_product_ids
                ])
                
                confirm_msg = f"""✅ Bạn đã chọn:

{product_list}

💰 Tổng tiền: {total:,.0f} {self.selected_product_ids[0].currency_id.symbol}

📋 Thông tin của bạn:
👤 Tên: {self.customer_name}
📞 SĐT: {self.customer_phone}

Bạn có muốn xác nhận đơn hàng không?
Trả lời "Có" để xác nhận, hoặc "Không" để hủy."""
                
                return {
                    'text': confirm_msg,
                    'quick_replies': [
                        {'content_type': 'text', 'title': '✅ Có', 'payload': 'CONFIRM_YES'},
                        {'content_type': 'text', 'title': '❌ Không', 'payload': 'CONFIRM_NO'},
                    ]
                }
                
            except ValueError:
                pass
        
        # If not valid product selection, ask again
        return {
            'text': 'Vui lòng chọn một sản phẩm từ danh sách bên trên.'
        }
    
    def _chatbot_create_order(self, user_message):
        """State 5: Tạo đơn hàng hoặc hủy"""
        if user_message == 'CONFIRM_YES' or user_message.lower() in ['có', 'yes', 'ok', 'đồng ý']:
            # Create messenger order
            order_vals = {
                'conversation_id': self.id,
                'facebook_user_id': self.facebook_user_id,
                'customer_name': self.customer_name,
                'customer_phone': self.customer_phone,
                'product_ids': [(6, 0, self.selected_product_ids.ids)],
                'company_id': self.company_id.id,
                'state': 'confirmed',
            }
            
            order = self.env['social.messenger.order'].create(order_vals)
            self.messenger_order_id = order.id
            
            # Create sale.order
            try:
                sale_order = order.create_sale_order()
                
                self.chatbot_state = 'completed'
                
                return {
                    'text': f"""🎉 Đặt hàng thành công!

Mã đơn hàng: {order.name}
Mã đơn bán hàng: {sale_order.name}

Chúng tôi sẽ liên hệ với bạn trong thời gian sớm nhất để xác nhận và giao hàng.

Cảm ơn bạn đã tin tưởng! 🙏"""
                }
            
            except Exception as e:
                _logger.error(f'Failed to create sale order: {e}')
                return {
                    'text': f'Đã có lỗi xảy ra khi tạo đơn hàng. Vui lòng liên hệ với chúng tôi qua hotline. Xin lỗi vì sự bất tiện này! 😔'
                }
        
        else:
            # Cancel order
            self.chatbot_state = 'idle'
            self.customer_name = False
            self.customer_phone = False
            self.selected_product_ids = [(5, 0, 0)]
            
            return {
                'text': 'Đơn hàng đã được hủy. Nếu bạn cần hỗ trợ, vui lòng gửi tin nhắn bất kỳ! 😊'
            }
    
    def send_chatbot_message(self, message_data):
        """
        Gửi tin nhắn chatbot qua Messenger.
        
        Args:
            message_data (dict): Message structure
                {
                    'text': 'Message text',
                    'quick_replies': [...]  (optional)
                }
        """
        self.ensure_one()
        
        if not message_data:
            return
        
        try:
            from odoo.addons.module_social_facebook.lib import facebook_api
            
            account = self.account_id
            if not account or not account.access_token:
                _logger.error(f'No access token for conversation {self.id}')
                return
            
            api = facebook_api.FacebookAPI(account.access_token)
            
            # Build message
            message = {'text': message_data['text']}
            
            if 'quick_replies' in message_data:
                message['quick_replies'] = message_data['quick_replies']
            
            # Send
            api.send_message(
                recipient_id=self.facebook_user_id,
                message=message
            )
            
            _logger.info(f'Sent chatbot message to {self.facebook_user_id}')
            
        except Exception as e:
            _logger.error(f'Failed to send chatbot message: {e}')
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CRM LEAD CREATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def create_lead_from_conversation(self):
        """
        Tạo crm.lead từ conversation.
        
        Returns:
            crm.lead: Lead record
        """
        self.ensure_one()
        
        if self.lead_id:
            _logger.warning(f'Lead already exists for conversation {self.id}')
            return self.lead_id
        
        # Check auto_create_lead setting
        auto_create = self.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.auto_create_lead', 'False'
        )
        if auto_create != 'True':
            return None
        
        # Build lead vals
        lead_vals = {
            'name': f'Facebook Lead: {self.customer_name or self.facebook_user_id}',
            'type': 'lead',
            'source_id': self._get_facebook_source(),
            'description': self._build_lead_description(),
            'company_id': self.company_id.id,
        }
        
        # Add contact info if available
        if self.customer_name:
            lead_vals['contact_name'] = self.customer_name
        if self.customer_phone:
            lead_vals['phone'] = self.customer_phone
        
        # Create lead
        lead = self.env['crm.lead'].create(lead_vals)
        self.lead_id = lead.id
        
        _logger.info(f'Created lead {lead.id} from conversation {self.id}')
        
        # Log activity
        lead.message_post(
            body=_('Lead created from Facebook Messenger conversation'),
            subject=_('Facebook Lead'),
        )
        
        return lead
    
    def _get_facebook_source(self):
        """Get or create 'Facebook' source"""
        Source = self.env['utm.source']
        source = Source.search([('name', '=', 'Facebook')], limit=1)
        if not source:
            source = Source.create({'name': 'Facebook'})
        return source.id
    
    def _build_lead_description(self):
        """Build description from conversation messages"""
        messages = self.env['social.message'].search([
            ('conversation_id', '=', self.id)
        ], order='created_date asc', limit=10)
        
        desc = "Conversation from Facebook Messenger:\n\n"
        for msg in messages:
            sender = 'Customer' if msg.is_from_customer else 'Page'
            desc += f"[{sender}] {msg.message}\n"
        
        return desc
# Tìm dòng cuối cùng của class SocialMessage (khoảng dòng 5413)
# Thêm các method sau trước dòng kết thúc class

    def _process_chatbot_response(self):
        """
        Process chatbot automation rules for incoming message
        Automatically send reply if matching rule found
        """
        self.ensure_one()
        
        # Only process inbound messages
        if self.message_type != 'inbound':
            return
        
        # Only process if conversation is active
        if self.conversation_id.state != 'active':
            return
        
        # Search for matching chatbot automation rule
        ChatbotRule = self.env['social.chatbot.automation']
        
        # Find active rules for this account
        rules = ChatbotRule.search([
            ('account_id', '=', self.account_id.id),
            ('active', '=', True),
            ('company_id', '=', self.company_id.id)
        ], order='priority desc, id')
        
        message_content_lower = (self.content or '').lower().strip()
        
        for rule in rules:
            trigger_keywords = [kw.strip().lower() for kw in (rule.trigger_keywords or '').split(',')]
            
            # Check if any keyword matches
            if any(keyword in message_content_lower for keyword in trigger_keywords if keyword):
                _logger.info(f"Chatbot rule matched: {rule.name} for message {self.id}")
                
                # Send automated response
                if rule.response_text:
                    try:
                        self._send_reply(rule.response_text)
                        
                        # Log activity to conversation chatter
                        self.conversation_id.message_post(
                            body=_("Automated response sent via chatbot rule: %s") % rule.name,
                            message_type='notification',
                            subtype_xmlid='mail.mt_note'
                        )
                        
                        # Check if this is purchase intent
                        purchase_keywords = ['mua', 'đặt hàng', 'order', 'buy', 'muốn mua', 'đặt mua']
                        if any(pk in message_content_lower for pk in purchase_keywords):
                            self.conversation_id._check_purchase_intent(self)
                        
                        # Only process first matching rule
                        break
                        
                    except Exception as e:
                        _logger.error(f"Error processing chatbot rule {rule.id}: {e}")
                        # Continue to next rule if this one fails
                        continue

    def _send_reply(self, reply_text):
        """
        Send reply message to Facebook and create outbound message record
        
        Args:
            reply_text (str): Text content to send
            
        Returns:
            social.message: Created outbound message record
        """
        self.ensure_one()
        
        conversation = self.conversation_id
        if not conversation or not conversation.facebook_psid:
            raise UserError(_("Invalid conversation - missing PSID"))
        
        account = conversation.account_id
        if not account or not account.access_token:
            raise UserError(_("Page access token not found"))
        
        # Get Facebook API instance
        fb_api = FacebookAPI()
        
        try:
            # Send message via Facebook Send API
            result = fb_api.send_message(
                recipient_id=conversation.facebook_psid,
                message_text=reply_text,
                page_access_token=account.access_token
            )
            
            # Create outbound message record
            outbound_message = self.env['social.message'].create({
                'conversation_id': conversation.id,
                'account_id': account.id,
                'message_type': 'outbound',
                'content': reply_text,
                'facebook_message_id': result.get('message_id'),
                'sent_date': fields.Datetime.now(),
                'company_id': self.company_id.id,
            })
            
            # Update conversation last message date
            conversation.write({
                'last_message_date': fields.Datetime.now()
            })
            
            _logger.info(f"Reply sent successfully. Message ID: {outbound_message.id}, FB ID: {result.get('message_id')}")
            
            return outbound_message
            
        except Exception as e:
            _logger.error(f"Failed to send reply for message {self.id}: {e}")
            raise