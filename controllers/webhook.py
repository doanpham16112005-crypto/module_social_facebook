import json
import logging
import requests
import re
from datetime import datetime, timedelta
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class FacebookWebhookController(http.Controller):
    
    @http.route('/social/facebook/webhook', type='http', auth='public', 
                methods=['GET'], csrf=False)
    def webhook_verify(self, **kwargs):
        """Verify webhook"""
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')
        
        verify_token = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.verify_token', '16112005'
        )
        
        if mode == 'subscribe' and token == verify_token:
            _logger.info('✅ Webhook verified')
            return challenge
        else:
            _logger.warning('❌ Webhook verify failed')
            return 'Forbidden', 403
    
    @http.route('/social/facebook/webhook', type='http', auth='public', 
                methods=['POST'], csrf=False)
    def webhook_callback(self, **kwargs):
        """Nhận events từ Facebook"""
        try:
            body = request.httprequest.get_data(as_text=True)
            
            _logger.info('=' * 80)
            _logger.info('📥 WEBHOOK RECEIVED')
            _logger.info(f'Body: {body}')
            _logger.info('=' * 80)
            
            data = json.loads(body)
            
            if data.get('object') != 'page':
                return 'OK'
            
            for entry in data.get('entry', []):
                self._process_entry(entry)
            
            return 'OK'
            
        except Exception as e:
            _logger.error('❌ Webhook error: %s', e, exc_info=True)
            return 'OK'
    
    def _process_entry(self, entry):
        if 'messaging' in entry:
            for event in entry['messaging']:
                self._process_messaging_event(event)
    
    def _process_messaging_event(self, event):
        """Process incoming message"""
        
        _logger.info('=' * 60)
        _logger.info('📨 MESSAGING EVENT')
        _logger.info(f'Event: {json.dumps(event, indent=2)}')
        _logger.info('=' * 60)
        
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        if not sender_id or not recipient_id:
            return
        
        msg = self._find_or_create_message_record(sender_id, recipient_id)
        if not msg:
            return
        
        # Check cooldown
        if msg.cooldown_until:
            now = fields.Datetime.now()
            if msg.cooldown_until > now:
                _logger.info(f"⏳ Cooldown active until {msg.cooldown_until}")
                return
        
        if 'message' in event:
            message_data = event['message']
            
            if message_data.get('is_echo'):
                return
            
            # ✅ FIX: XỬ LÝ STICKER & ATTACHMENT
            user_message = ''
            
            # Kiểm tra có text không
            if 'text' in message_data:
                user_message = message_data.get('text', '')
                _logger.info(f'💬 Text message: {user_message}')
            
            # ✅ THÊM: Xử lý sticker/attachment → Bỏ qua
            elif 'attachments' in message_data:
                attachments = message_data.get('attachments', [])
                _logger.info(f'📎 Received attachment/sticker (count: {len(attachments)})')
                
                # Kiểm tra có phải sticker không
                if attachments and attachments[0].get('type') == 'image':
                    payload = attachments[0].get('payload', {})
                    if 'sticker_id' in payload:
                        _logger.info(f'👍 Sticker detected: {payload.get("sticker_id")}')
                        # Phản hồi thân thiện
                        self._send_text(msg, '😊 Cảm ơn bạn!\n\n👉 Gửi "mua" để xem sản phẩm nhé!')
                        return
                
                # Attachment khác (image, file...) → Bỏ qua
                _logger.info(f'📎 Non-text message, ignoring')
                return
            
            # Process quick reply
            if 'quick_reply' in message_data:
                payload = message_data['quick_reply'].get('payload', '')
                _logger.info(f'⚡ Quick reply payload: {payload}')
                self._process_chatbot_flow(msg, payload)
            elif user_message:
                # Chỉ xử lý khi có text
                self._process_chatbot_flow(msg, user_message)
    
    def _find_or_create_message_record(self, sender_id, recipient_id):
        """Tìm/tạo message record"""
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)
        ], limit=1)
        
        if not account:
            return None
        
        msg = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', sender_id),
            ('account_id', '=', account.id),
        ], limit=1)
        
        if msg:
            return msg
        
        try:
            return request.env['social.message'].sudo().create({
                'facebook_user_id': sender_id,
                'account_id': account.id,
                'company_id': account.company_id.id,
                'chatbot_state': 'idle',
            })
        except Exception as e:
            _logger.error(f"Failed to create message record: {e}")
            return None
    
    def _find_existing_customer(self, psid):
        """Tìm customer theo TAG facebook_psid:xxx"""
        try:
            _logger.info(f'🔎 Searching for customer with PSID: {psid}')
            
            Partner = request.env['res.partner'].sudo()
            Tag = request.env['res.partner.category'].sudo()
            
            psid_tag = Tag.search([('name', '=', "facebook_psid:{psid}")], limit=1)
            
            if not psid_tag:
                _logger.info(f"❌ No PSID tag found")
                return None
            
            partner = Partner.search([
                ('category_id', 'in', [psid_tag.id]),
            ], limit=1)
            
            if partner:
                _logger.info(f"✅ FOUND customer: {partner.name}")
            
            return partner
            
        except Exception as e:
            _logger.error(f"❌ ERROR: {e}", exc_info=True)
            return None
    
    def _get_or_create_psid_tag(self, psid):
        """Tạo/lấy PSID tag"""
        Tag = request.env['res.partner.category'].sudo()
        tag = Tag.search([('name', '=', f"facebook_psid:{psid}")], limit=1)
        if not tag:
            tag = Tag.create({'name': f"facebook_psid:{psid}", 'color': 5})
        return tag
    
    def _get_or_create_fb_messenger_tag(self):
        """Tạo/lấy FB Messenger tag"""
        Tag = request.env['res.partner.category'].sudo()
        tag = Tag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
        if not tag:
            tag = Tag.create({'name': 'Facebook-Messenger', 'color': 4})
        return tag
    
    def _reset_order_flow(self, msg, kick_start=False, set_cooldown=False):
        """Reset order flow"""
        write_vals = {
            'chatbot_state': 'idle',
            'cooldown_until': False,
            'selected_product_ids': [(5, 0, 0)],
            'product_quantity': 0,
            'customer_name': False,
            'customer_phone': False,
            'customer_address': False,
        }
        
        if set_cooldown:
            write_vals['cooldown_until'] = fields.Datetime.now() + timedelta(seconds=3)
        
        msg.sudo().write(write_vals)
        _logger.info(f"🔄 Reset order flow for PSID: {msg.facebook_user_id}")
        
        if kick_start:
            self._state_idle(msg, 'mua')
    
    def _process_chatbot_flow(self, msg, user_message):
        """Process chatbot flow"""
        
        _logger.info('=' * 60)
        _logger.info('🤖 CHATBOT FLOW')
        _logger.info(f'PSID: {msg.facebook_user_id}')
        _logger.info(f'Message: {user_message}')
        _logger.info(f'Current state: {msg.chatbot_state}')
        _logger.info('=' * 60)
        
        state = msg.chatbot_state or 'idle'
        
        if state == 'idle':
            self._state_idle(msg, user_message)
        elif state == 'ask_update':
            self._state_ask_update(msg, user_message)
        elif state == 'ask_name':
            self._state_ask_name(msg, user_message)
        elif state == 'ask_phone':
            self._state_ask_phone(msg, user_message)
        elif state == 'ask_address':
            self._state_ask_address(msg, user_message)
        elif state == 'show_products':
            self._state_show_products(msg, user_message)
        elif state == 'ask_quantity':
            self._state_ask_quantity(msg, user_message)
        elif state == 'confirm_order':
            self._state_confirm_order(msg, user_message)
    
    def _state_idle(self, msg, text):
        """State: idle"""
        _logger.info('🎬 STATE: IDLE')
        
        text_lower = text.lower().strip()
        
        # Tìm customer
        customer = self._find_existing_customer(msg.facebook_user_id)
        
        if customer:
            _logger.info(f"👤 Returning customer: {customer.name}")
            self._greet_returning_customer(msg, customer, text)
            return
        
        _logger.info("🆕 New customer")
        
        # Xử lý PRODUCT payload
        if text.startswith('PRODUCT_'):
            msg.sudo().write({'chatbot_state': 'show_products'})
            self._state_show_products(msg, text)
            return
        
        # Kiểm tra từ khóa mua
        if any(kw in text_lower for kw in ['mua', 'order', 'buy', 'menu']):
            _logger.info("🛒 'mua' keyword - starting registration")
            msg.sudo().write({'chatbot_state': 'ask_name'})
            
            welcome_msg = request.env['ir.config_parameter'].sudo().get_param(
                'module_social_facebook.chatbot_welcome_message',
                'Xin chào! 👋\n\nBạn vui lòng cho biết tên của bạn?'
            )
            
            self._send_text(msg, welcome_msg)
        else:
            self._send_text(msg, '👋 Xin chào! Gửi "mua" để xem sản phẩm!')
    
    def _greet_returning_customer(self, msg, customer, user_message):
        """Chào khách quen"""
        _logger.info(f'👋 Greeting customer: {customer.name}')
        
        msg.sudo().write({
            'customer_name': customer.name,
            'customer_phone': customer.phone,
            'customer_address': customer.street,
        })
        
        text_lower = user_message.lower().strip()
        
        if user_message.startswith('PRODUCT_'):
            msg.sudo().write({'chatbot_state': 'show_products'})
            self._state_show_products(msg, user_message)
            return
        
        if any(kw in text_lower for kw in ['mua', 'order', 'buy', 'menu']):
            msg.sudo().write({'chatbot_state': 'ask_update'})
            
            message = f"""👋 Xin chào {customer.name}!

📞 SĐT: {customer.phone or 'Chưa có'}
📍 Địa chỉ: {customer.street or 'Chưa có'}

Bạn có muốn cập nhật thông tin không?
👉 Gửi "Có" để cập nhật
👉 Gửi "Không" để tiếp tục mua hàng"""
            
            self._send_text(msg, message)
        else:
            message = f"""👋 Xin chào {customer.name}!

Rất vui được gặp lại bạn! 😊

👉 Gửi "mua" để xem sản phẩm"""
            
            self._send_text(msg, message)
    
    def _state_ask_update(self, msg, text):
        """State: ask_update"""
        text_lower = text.lower().strip()
        
        if any(kw in text_lower for kw in ['có', 'yes', 'ok']):
            msg.sudo().write({'chatbot_state': 'ask_name'})
            self._send_text(msg, "Bạn muốn cập nhật tên?\n(gửi '.' để giữ nguyên)")
        elif any(kw in text_lower for kw in ['không', 'no', 'skip', 'mua']):
            msg.sudo().write({'chatbot_state': 'show_products'})
            self._send_product_list(msg)
        else:
            self._send_text(msg, '❓ Gửi "Có" hoặc "Không"')
    
    def _state_ask_name(self, msg, text):
        """State: ask_name"""
        text_lower = text.lower().strip()
        
        if any(kw in text_lower for kw in ['mua', 'menu']):
            msg.sudo().write({'chatbot_state': 'idle'})
            self._state_idle(msg, text)
            return
        
        name = text.strip()
        
        if name == '.':
            if msg.customer_name:
                msg.sudo().write({'chatbot_state': 'ask_phone'})
                self._send_text(msg, "✅ Giữ nguyên tên.\n\nNhập SĐT?\n(gửi '.' để giữ nguyên)")
                return
            else:
                self._send_text(msg, "❌ Vui lòng nhập tên!")
                return
        
        if len(name) < 2:
            self._send_text(msg, "❌ Tên quá ngắn.")
            return
        
        name_normalized = ' '.join(word.capitalize() for word in name.split())
        
        msg.sudo().write({
            'customer_name': name_normalized,
            'chatbot_state': 'ask_phone'
        })
        
        self._send_text(msg, f"✅ Xin chào {name_normalized}! 😊\n\nNhập SĐT?\n(gửi '.' để giữ nguyên)")
    
    def _state_ask_phone(self, msg, text):
        """State: ask_phone"""
        text_lower = text.lower().strip()
        
        if any(kw in text_lower for kw in ['mua', 'menu']):
            msg.sudo().write({'chatbot_state': 'idle'})
            self._state_idle(msg, text)
            return
        
        phone = text.strip()
        
        if phone == '.':
            if msg.customer_phone:
                msg.sudo().write({'chatbot_state': 'ask_address'})
                self._send_text(msg, "✅ Giữ nguyên SĐT.\n\nNhập địa chỉ?\n(gửi '.' để giữ nguyên)")
                return
            else:
                self._send_text(msg, "❌ Vui lòng nhập SĐT!")
                return
        
        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)
        
        if phone_clean.startswith('+84'):
            phone_clean = '0' + phone_clean[3:]
        elif phone_clean.startswith('84'):
            phone_clean = '0' + phone_clean[2:]
        
        if not re.match(r'^0\d{9,10}$', phone_clean):
            self._send_text(msg, "📱 SĐT không hợp lệ!\n\nVD: 0912345678")
            return
        
        msg.sudo().write({
            'customer_phone': phone_clean,
            'chatbot_state': 'ask_address'
        })
        
        self._send_text(msg, "📍 Nhập địa chỉ giao hàng?\n(gửi '.' để giữ nguyên)")
    
    def _state_ask_address(self, msg, text):
        """State: ask_address"""
        text_lower = text.lower().strip()
        
        if any(kw in text_lower for kw in ['mua', 'menu']):
            msg.sudo().write({'chatbot_state': 'idle'})
            self._state_idle(msg, text)
            return
        
        address = text.strip()
        
        if address == '.':
            if msg.customer_address:
                msg.sudo().write({'chatbot_state': 'show_products'})
                self._send_text(msg, "✅ Giữ nguyên địa chỉ.")
                self._send_product_list(msg)
                return
            else:
                self._send_text(msg, "❌ Vui lòng nhập địa chỉ!")
                return
        
        if len(address) < 5:
            self._send_text(msg, "❌ Địa chỉ quá ngắn!")
            return
        
        msg.sudo().write({
            'customer_address': address,
            'chatbot_state': 'show_products'
        })
        
        self._send_product_list(msg)
    
    def _state_show_products(self, msg, text):
        """State: show_products"""
        if text.startswith('PRODUCT_'):
            product_id = self._extract_product_id(text)
            if product_id:
                self._handle_product_selection(msg, product_id)
    
    def _state_ask_quantity(self, msg, text):
        """State: ask_quantity"""
        try:
            quantity = int(text.strip())
            
            if quantity < 1:
                self._send_text(msg, "❌ Số lượng >= 1")
                return
            
            if quantity > 999:
                self._send_text(msg, "❌ Max 999")
                return
            
            msg.sudo().write({
                'product_quantity': quantity,
                'chatbot_state': 'confirm_order'
            })
            
            product = msg.selected_product_ids[0]
            total = product.price * quantity
            
            self._send_text(msg, f"""✅ Xác nhận:

📦 {product.product_id.name}
🔢 SL: {quantity}
💰 Đơn giá: {product.price:,.0f} đ
💵 Tổng: {total:,.0f} đ

👤 {msg.customer_name}
📞 {msg.customer_phone}
📍 {msg.customer_address or 'Chưa có'}

Xác nhận?
👉 "Có" / "Không" """)
            
        except ValueError:
            self._send_text(msg, "❌ Nhập số (VD: 1, 2, 5)")
    
    def _state_confirm_order(self, msg, text):
        """State: confirm_order"""
        text_lower = text.lower().strip()
        
        if any(kw in text_lower for kw in ['có', 'yes', 'ok']):
            try:
                partner = self._find_or_create_partner_with_tags(msg)
                order = self._create_sale_order(msg, partner)
                lead = self._create_or_update_crm_lead(msg, partner, order)
                self._sync_to_conversation(msg, partner, lead)
                
                self._send_text(msg, f"""🎉 Đặt hàng thành công!

📝 Mã: {order.name}
💰 Tổng: {order.amount_total:,.0f} đ

Cảm ơn! 🙏
👉 Gửi "mua" để tiếp tục""")
                
                self._reset_order_flow(msg, set_cooldown=True)
                
            except Exception as e:
                _logger.error(f'Order failed: {e}', exc_info=True)
                self._reset_order_flow(msg)
                self._send_text(msg, "❌ Lỗi! Thử lại")
        
        elif any(kw in text_lower for kw in ['không', 'no']):
            msg.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)],
                'product_quantity': 0,
            })
            self._send_text(msg, "❌ Đã hủy. Chọn lại!")
            self._send_product_list(msg)
        else:
            self._send_text(msg, '❓ Gửi "Có" hoặc "Không"')
    
    def _find_or_create_partner_with_tags(self, msg):
        """Tạo/cập nhật partner"""
        Partner = request.env['res.partner'].with_context(tracking_disable=True).sudo()
        
        existing = self._find_existing_customer(msg.facebook_user_id)
        
        if existing:
            update_vals = {}
            if msg.customer_name and existing.name != msg.customer_name:
                update_vals['name'] = msg.customer_name
            if msg.customer_phone and existing.phone != msg.customer_phone:
                update_vals['phone'] = msg.customer_phone
            if msg.customer_address and existing.street != msg.customer_address:
                update_vals['street'] = msg.customer_address
            
            if update_vals:
                existing.write(update_vals)
            
            return existing
        else:
            fb_tag = self._get_or_create_fb_messenger_tag()
            psid_tag = self._get_or_create_psid_tag(msg.facebook_user_id)
            
            return Partner.create({
                'name': msg.customer_name,
                'phone': msg.customer_phone,
                'street': msg.customer_address,
                'company_type': 'person',
                'category_id': [(6, 0, [fb_tag.id, psid_tag.id])],
            })
    
    def _create_sale_order(self, msg, partner):
        """Tạo sale order"""
        SaleOrder = request.env['sale.order'].with_context(tracking_disable=True).sudo()
        OrderLine = request.env['sale.order.line'].with_context(tracking_disable=True).sudo()
        
        order = SaleOrder.create({
            'partner_id': partner.id,
            'date_order': fields.Datetime.now(),
        })
        
        for product in msg.selected_product_ids:
            OrderLine.create({
                'order_id': order.id,
                'product_id': product.product_id.id,
                'product_uom_qty': msg.product_quantity or 1,
                'price_unit': product.price,
            })
        
        return order
    
    def _create_or_update_crm_lead(self, msg, partner, order):
        """Tạo/cập nhật CRM Lead"""
        try:
            Lead = request.env['crm.lead'].with_context(tracking_disable=True).sudo()
            LeadTag = request.env['crm.tag'].sudo()
            
            psid_tag = LeadTag.search([('name', '=', f"facebook_psid:{msg.facebook_user_id}")], limit=1)
            if not psid_tag:
                psid_tag = LeadTag.create({'name': f"facebook_psid:{msg.facebook_user_id}", 'color': 5})
            
            existing_lead = Lead.search([
                ('tag_ids', 'in', [psid_tag.id]),
                ('partner_id', '=', partner.id),
            ], limit=1)
            
            if existing_lead:
                new_revenue = (existing_lead.expected_revenue or 0) + order.amount_total
                existing_lead.write({'expected_revenue': new_revenue})
                msg.sudo().write({'lead_id': existing_lead.id})
                return existing_lead
            else:
                lead = Lead.create({
                    'name': f'FB Lead - {partner.name}',
                    'type': 'opportunity',
                    'partner_id': partner.id,
                    'contact_name': partner.name,
                    'phone': partner.phone,
                    'expected_revenue': order.amount_total,
                    'tag_ids': [(6, 0, [psid_tag.id])],
                })
                msg.sudo().write({'lead_id': lead.id})
                return lead
        except Exception as e:
            _logger.error(f"Lead error: {e}", exc_info=True)
            return None
    
    def _sync_to_conversation(self, msg, partner, lead):
        """Sync to conversation"""
        try:
            Conversation = request.env['social.conversation'].sudo()
            
            existing = Conversation.search([
                ('facebook_psid', '=', msg.facebook_user_id),
                ('account_id', '=', msg.account_id.id),
            ], limit=1)
            
            conv_vals = {
                'customer_name': partner.name,
                'customer_phone': partner.phone,
                'last_message_date': fields.Datetime.now(),
                'state': 'ongoing',
                'lead_id': lead.id if lead else False,
            }
            
            if existing:
                existing.write(conv_vals)
            else:
                conv_vals.update({
                    'facebook_psid': msg.facebook_user_id,
                    'account_id': msg.account_id.id,
                    'company_id': msg.company_id.id,
                    'conversation_id': f"CONV-{Conversation.search_count([]) + 1:05d}",
                })
                Conversation.create(conv_vals)
        except Exception as e:
            _logger.error(f"Conversation error: {e}", exc_info=True)
    
    def _handle_product_selection(self, msg, product_id):
        """Handle product selection"""
        product = request.env['social.messenger.product'].sudo().browse(product_id)
        
        if not product.exists():
            self._send_text(msg, "❌ Không tồn tại!")
            return
        
        msg.sudo().write({
            'selected_product_ids': [(6, 0, [product.id])],
            'chatbot_state': 'ask_quantity'
        })
        
        self._send_text(msg, f"""✅ Đã chọn: {product.product_id.name}

💰 Giá: {product.price:,.0f} đ

🔢 Nhập số lượng (VD: 1, 2, 5)""")
    
    def _send_text(self, msg, text):
        """Send text"""
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': msg.facebook_user_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': msg.account_id.access_token}
        
        try:
            requests.post(url, json=payload, params=params, timeout=10)
        except Exception as e:
            _logger.error(f"Send error: {e}")
    
    def _send_product_list(self, msg):
        """Send product list"""
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', msg.company_id.id)
        ], order='sequence, id')
        
        if not products:
            self._send_text(msg, "❌ Chưa có sản phẩm!")
            return
        
        product_list = "📦 DANH SÁCH SẢN PHẨM\n\n"
        
        for idx, p in enumerate(products, 1):
            price = f"{p.price:,.0f} đ" if p.price > 0 else "Liên hệ"
            product_list += f"{idx}. {p.product_id.name}\n   💰 {price}\n\n"
        
        product_list += "👇 Chọn sản phẩm:"
        
        quick_replies = []
        for p in products[:11]:
            quick_replies.append({
                'content_type': 'text',
                'title': p.quick_reply_title or p.product_id.name[:20],
                'payload': f'PRODUCT_{p.id}'
            })
        
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': msg.facebook_user_id},
            'message': {
                'text': product_list,
                'quick_replies': quick_replies
            },
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': msg.account_id.access_token}
        
        try:
            requests.post(url, json=payload, params=params, timeout=10)
        except Exception as e:
            _logger.error(f"Product list error: {e}")
    
    def _validate_order_data(self, msg):
        """Validate"""
        errors = []
        if not msg.customer_name: errors.append("Tên")
        if not msg.customer_phone: errors.append("SĐT")
        if not msg.customer_address: errors.append("Địa chỉ")
        if not msg.selected_product_ids: errors.append("SP")
        if not msg.product_quantity: errors.append("SL")
        return {'valid': len(errors) == 0, 'errors': ', '.join(errors)}
    
    def _extract_product_id(self, payload):
        """Extract product ID"""
        try:
            return int(payload.replace('PRODUCT_', ''))
        except:
            return None