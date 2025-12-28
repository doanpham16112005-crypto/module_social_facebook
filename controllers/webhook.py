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
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        if not sender_id or not recipient_id:
            return
        
        conversation = self._find_or_create_conversation(sender_id, recipient_id)
        if not conversation:
            return
        
        if 'message' in event:
            message_data = event['message']
            
            if message_data.get('is_echo'):
                return
            
            if 'quick_reply' in message_data:
                payload = message_data['quick_reply'].get('payload', '')
                self._process_chatbot_flow(conversation, payload)
            else:
                text = message_data.get('text', '')
                self._process_chatbot_flow(conversation, text)
    
    # =========================================================================
    # ✅✅✅ HELPER: TÌM CUSTOMER CÓ 2 TAG (NGHIÊM TÚC)
    # =========================================================================
    
    def _find_existing_customer(self, psid):
        """
        ✅ YÊU CẦU 1 - TIÊU CHÍ 1
        
        Tìm customer có ĐỦ 2 tag:
        - "Facebook-Messenger"
        - "facebook_psid:XXXXX"
        
        Returns:
            res.partner record hoặc None
        """
        try:
            Partner = request.env['res.partner'].sudo()
            Tag = request.env['res.partner.category'].sudo()
            
            # 1. Tìm tag "facebook_psid:XXXXX"
            psid_tag_name = f"facebook_psid:{psid}"
            psid_tag = Tag.search([('name', '=', psid_tag_name)], limit=1)
            
            if not psid_tag:
                _logger.info(f"⚠️ PSID tag '{psid_tag_name}' not found")
                return None
            
            # 2. Tìm tag "Facebook-Messenger"
            fb_tag = Tag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
            
            if not fb_tag:
                _logger.info("⚠️ Facebook-Messenger tag not found")
                return None
            
            # 3. Tìm partner có CẢ 2 TAG
            partners = Partner.search([
                ('category_id', 'in', [psid_tag.id, fb_tag.id]),
            ])
            
            # 4. Kiểm tra partner nào có ĐỦ 2 tag
            for partner in partners:
                tag_ids = partner.category_id.ids
                if psid_tag.id in tag_ids and fb_tag.id in tag_ids:
                    _logger.info(f"✅ Found customer: {partner.name} (ID: {partner.id})")
                    return partner
            
            _logger.info(f"⚠️ No customer found with both tags for PSID: {psid}")
            return None
            
        except Exception as e:
            _logger.error(f"❌ Error finding customer: {e}")
            return None
    
    def _get_or_create_psid_tag(self, psid):
        """Tạo hoặc lấy tag facebook_psid:XXXXX"""
        Tag = request.env['res.partner.category'].sudo()
        tag_name = f"facebook_psid:{psid}"
        
        tag = Tag.search([('name', '=', tag_name)], limit=1)
        if not tag:
            tag = Tag.create({'name': tag_name, 'color': 5})
            _logger.info(f"✅ Created PSID tag: {tag_name}")
        
        return tag
    
    def _get_or_create_fb_messenger_tag(self):
        """Tạo hoặc lấy tag Facebook-Messenger"""
        Tag = request.env['res.partner.category'].sudo()
        
        tag = Tag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
        if not tag:
            tag = Tag.create({'name': 'Facebook-Messenger', 'color': 4})
            _logger.info("✅ Created Facebook-Messenger tag")
        
        return tag
    
    # =========================================================================
    # ✅✅✅ CHATBOT FLOW (NGHIÊM TÚC)
    # =========================================================================
    
    def _process_chatbot_flow(self, conversation, user_message):
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            return
        
        if self._is_in_cooldown(conversation):
            self._send_text(conversation, 
                "Cảm ơn bạn đã đặt hàng! Đơn hàng đang được xử lý. Đợi 1 phút để nhắn lại 😊")
            return
        
        current_state = conversation.chatbot_state or 'idle'
        _logger.info(f'🤖 CHATBOT STATE: {current_state} | Message: {user_message}')
        
        # ✅ ROUTING
        if current_state == 'idle':
            self._state_idle(conversation, user_message)
        elif current_state == 'ask_update':
            self._state_ask_update(conversation, user_message)
        elif current_state == 'ask_name':
            self._state_ask_name(conversation, user_message)
        elif current_state == 'ask_phone':
            self._state_ask_phone(conversation, user_message)
        elif current_state == 'ask_address':
            self._state_ask_address(conversation, user_message)
        elif current_state == 'show_products':
            self._state_show_products(conversation, user_message)
        elif current_state == 'ask_quantity':
            self._state_ask_quantity(conversation, user_message)
        elif current_state == 'confirm_order':
            self._state_confirm_order(conversation, user_message)
        elif current_state == 'completed':
            self._state_completed(conversation, user_message)
    
    def _state_idle(self, conv, msg):
        """
        ✅ YÊU CẦU 1 - TIÊU CHÍ 1
        
        State IDLE: Kiểm tra customer có 2 tag chưa
        """
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['mua', 'order', 'buy', 'menu', 'sản phẩm']):
            
            # ✅ KIỂM TRA COOLDOWN TRƯỚC (tránh spam)
            if self._is_in_cooldown(conv):
                # ✅ TRONG COOLDOWN → VẪN CHO PHÉP MUA TIẾP
                # Chỉ cảnh báo nhẹ, không block
                pass
            
            # ✅ BƯỚC 1: Kiểm tra customer có 2 tag chưa
            existing_customer = self._find_existing_customer(conv.facebook_user_id)
            
            if existing_customer:
                # ✅ CÓ CUSTOMER → Chào + Hỏi cập nhật
                _logger.info(f"✅ Customer exists: {existing_customer.name}")
                
                conv.sudo().write({
                    'chatbot_state': 'ask_update',
                    'customer_name': existing_customer.name,
                    'customer_phone': existing_customer.phone,
                    'customer_address': existing_customer.street,
                })
                
                greeting_msg = f"""👋 Xin chào lại {existing_customer.name}!

    📞 SĐT: {existing_customer.phone or 'Chưa có'}
    📍 Địa chỉ: {existing_customer.street or 'Chưa có'}

    Bạn có muốn cập nhật thông tin không?
    👉 Gửi "Có" để cập nhật
    👉 Gửi "Không" để tiếp tục mua hàng"""
                
                self._send_text(conv, greeting_msg)
                
            else:
                # ✅ CHƯA CÓ CUSTOMER → Flow hỏi như cũ
                _logger.info(f"⚠️ New customer (PSID: {conv.facebook_user_id})")
                
                conv.sudo().write({'chatbot_state': 'ask_name'})
                
                welcome_msg = request.env['ir.config_parameter'].sudo().get_param(
                    'module_social_facebook.chatbot_welcome_message',
                    'Xin chào! 👋\n\nBạn vui lòng cho biết tên của bạn?'
                )
                
                self._send_text(conv, welcome_msg)
        else:
            self._send_text(conv, '👋 Gửi "mua" để xem sản phẩm!')
    
    def _state_ask_update(self, conv, msg):
        """
        ✅ STATE MỚI: Hỏi customer cũ có muốn cập nhật không
        """
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['có', 'yes', 'ok', 'update', 'cập nhật']):
            # Muốn cập nhật → Hỏi lại từ đầu
            conv.sudo().write({'chatbot_state': 'ask_name'})
            self._send_text(conv, "Bạn muốn cập nhật tên mới?\n(hoặc gửi '.' để giữ nguyên)")
        
        elif any(kw in msg_lower for kw in ['không', 'no', 'skip', 'bỏ qua']):
            # Không cập nhật → Vào show_products luôn
            conv.sudo().write({'chatbot_state': 'show_products'})
            self._send_product_list(conv)
        
        else:
            self._send_text(conv, '❓ Vui lòng gửi "Có" hoặc "Không"')
    
    def _state_ask_name(self, conv, msg):
        """Hỏi tên (cho phép giữ nguyên với '.')"""
        name = msg.strip()
        
        # Nếu gửi '.' → giữ nguyên
        if name == '.':
            if conv.customer_name:
                conv.sudo().write({'chatbot_state': 'ask_phone'})
                self._send_text(conv, "✅ Giữ nguyên tên.\n\nBạn muốn cập nhật SĐT?\n(hoặc gửi '.' để giữ nguyên)")
                return
            else:
                self._send_text(conv, "❌ Bạn chưa có tên. Vui lòng nhập tên!")
                return
        
        if len(name) < 2:
            self._send_text(conv, "❌ Tên quá ngắn. Vui lòng nhập lại.")
            return
        
        # Chuẩn hóa tên: Viết hoa chữ cái đầu
        name_normalized = ' '.join(word.capitalize() for word in name.split())
        
        conv.sudo().write({
            'customer_name': name_normalized,
            'chatbot_state': 'ask_phone'
        })
        
        self._send_text(conv, f"✅ Xin chào {name_normalized}! 😊\n\nBạn vui lòng cung cấp số điện thoại?\n(hoặc gửi '.' để giữ nguyên)")
    
    def _state_ask_phone(self, conv, msg):
        """Hỏi SĐT (cho phép giữ nguyên với '.')"""
        phone = msg.strip()
        
        # Nếu gửi '.' → giữ nguyên
        if phone == '.':
            if conv.customer_phone:
                conv.sudo().write({'chatbot_state': 'ask_address'})
                self._send_text(conv, "✅ Giữ nguyên SĐT.\n\nBạn muốn cập nhật địa chỉ?\n(hoặc gửi '.' để giữ nguyên)")
                return
            else:
                self._send_text(conv, "❌ Bạn chưa có SĐT. Vui lòng nhập SĐT!")
                return
        
        # Chuẩn hóa phone
        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)
        
        if phone_clean.startswith('+84'):
            phone_clean = '0' + phone_clean[3:]
        elif phone_clean.startswith('84'):
            phone_clean = '0' + phone_clean[2:]
        
        if not re.match(r'^0\d{9,10}$', phone_clean):
            self._send_text(conv, 
                "📱 Số điện thoại không hợp lệ!\n\nVui lòng nhập lại (VD: 0912345678)")
            return
        
        conv.sudo().write({
            'customer_phone': phone_clean,
            'chatbot_state': 'ask_address'
        })
        
        self._send_text(conv, "📍 Bạn vui lòng cung cấp địa chỉ giao hàng?\n(hoặc gửi '.' để giữ nguyên)")
    
    def _state_ask_address(self, conv, msg):
        """Hỏi địa chỉ (cho phép giữ nguyên với '.')"""
        address = msg.strip()
        
        # Nếu gửi '.' → giữ nguyên
        if address == '.':
            if conv.customer_address:
                conv.sudo().write({'chatbot_state': 'show_products'})
                self._send_text(conv, "✅ Giữ nguyên địa chỉ.")
                self._send_product_list(conv)
                return
            else:
                self._send_text(conv, "❌ Bạn chưa có địa chỉ. Vui lòng nhập địa chỉ!")
                return
        
        if len(address) < 5:
            self._send_text(conv, "❌ Địa chỉ quá ngắn. Vui lòng nhập đầy đủ địa chỉ!")
            return
        
        conv.sudo().write({
            'customer_address': address,
            'chatbot_state': 'show_products'
        })
        
        self._send_product_list(conv)
    
    def _state_show_products(self, conv, msg):
        """Hiển thị danh sách sản phẩm"""
        if msg.startswith('PRODUCT_'):
            product_id = self._extract_product_id(msg)
            if product_id:
                self._handle_product_selection(conv, product_id)
    
    def _state_ask_quantity(self, conv, msg):
        """Hỏi số lượng sản phẩm"""
        try:
            quantity = int(msg.strip())
            
            if quantity < 1:
                self._send_text(conv, "❌ Số lượng phải >= 1. Vui lòng nhập lại!")
                return
            
            if quantity > 999:
                self._send_text(conv, "❌ Số lượng quá lớn (max 999). Vui lòng nhập lại!")
                return
            
            conv.sudo().write({
                'product_quantity': quantity,
                'chatbot_state': 'confirm_order'
            })
            
            product = conv.selected_product_ids[0]
            price_unit = product.price
            total = price_unit * quantity
            
            confirm_msg = f"""✅ Xác nhận đơn hàng:

📦 Sản phẩm: {product.product_id.name}
🔢 Số lượng: {quantity}
💰 Đơn giá: {price_unit:,.0f} đ
💵 Tổng tiền: {total:,.0f} đ

👤 Khách hàng: {conv.customer_name}
📞 SĐT: {conv.customer_phone}
📍 Địa chỉ: {conv.customer_address or 'Chưa có'}

Xác nhận đặt hàng?
👉 "Có" / "Không" """
            
            self._send_text(conv, confirm_msg)
            
        except ValueError:
            self._send_text(conv, "❌ Vui lòng nhập số lượng hợp lệ (ví dụ: 1, 2, 5...)")
    
    def _state_confirm_order(self, conv, msg):
        """
        ✅ YÊU CẦU 1 - TIÊU CHÍ 2 + YÊU CẦU 3
        
        Xác nhận đơn hàng:
        - Tạo/Cập nhật partner với 2 tag
        - Tạo sale order
        - Tạo/Cập nhật CRM Lead (cộng dồn revenue)
        - Sync social.conversation
        """
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['có', 'yes', 'ok', 'đồng ý', 'xác nhận']):
            
            try:
                # Validate
                validation = self._validate_order_data(conv)
                if not validation['valid']:
                    self._send_text(conv, f"❌ Dữ liệu không hợp lệ: {validation['errors']}")
                    return
                
                # ✅ BƯỚC 1: Tạo/Cập nhật PARTNER với 2 TAG
                partner = self._find_or_create_partner_with_tags(conv)
                
                # ✅ BƯỚC 2: Tạo SALE ORDER
                order = self._create_sale_order(conv, partner)
                
                # ✅ BƯỚC 3: Tạo/Cập nhật CRM LEAD (cộng dồn)
                lead = self._create_or_update_crm_lead(conv, partner, order)
                
                # ✅ BƯỚC 4: Sync SOCIAL.CONVERSATION
                self._sync_to_conversation(conv, partner, lead)
                
                # ✅ SUCCESS MESSAGE
                success_msg = f"""🎉 Đặt hàng thành công!

📝 Mã đơn hàng: {order.name}
👤 Khách hàng: {conv.customer_name}
📞 SĐT: {conv.customer_phone}
📍 Địa chỉ: {conv.customer_address or 'Chưa cập nhật'}
💰 Tổng tiền: {order.amount_total:,.0f} đ

✅ Đơn hàng đã được ghi nhận!
✅ Thông tin đã được lưu vào hệ thống CRM!

Cảm ơn bạn! 🙏"""
                
                self._send_text(conv, success_msg)
                
                conv.sudo().write({'chatbot_state': 'completed'})
                self._set_cooldown(conv)
                
            except Exception as e:
                import traceback
                _logger.error('❌ ORDER FAILED: %s', str(e))
                _logger.error(traceback.format_exc())
                
                conv.sudo().write({'chatbot_state': 'idle'})
                self._send_text(conv, "❌ Có lỗi xảy ra khi tạo đơn hàng. Vui lòng thử lại!")
        
        elif any(kw in msg_lower for kw in ['không', 'no', 'hủy']):
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)],
                'product_quantity': 0,
            })
            self._send_text(conv, "❌ Đã hủy. Bạn có thể chọn lại sản phẩm!")
            self._send_product_list(conv)
        else:
            self._send_text(conv, '❓ Vui lòng gửi "Có" hoặc "Không"')
    
    def _state_completed(self, conv, msg):
        """
        ✅ SỬA: State hoàn tất
        
        Sau khi order xong:
        - Xóa cooldown (cho phép order ngay lập tức)
        - Reset về idle
        - Cho phép customer mua tiếp
        """
        # ✅ XÓA COOLDOWN để cho phép mua tiếp
        conv.sudo().write({
            'chatbot_state': 'idle',
            'cooldown_until': False,  # ✅ XÓA COOLDOWN
        })
        
        # ✅ Xử lý message tiếp theo như idle
        self._state_idle(conv, msg)
    
    # =========================================================================
    # ✅✅✅ HELPER: TẠO/CẬP NHẬT PARTNER với 2 TAG
    # =========================================================================
    
    def _find_or_create_partner_with_tags(self, conv):
        """
        ✅ YÊU CẦU 1 - TIÊU CHÍ 1
        
        Tìm hoặc tạo partner với 2 tag:
        - "Facebook-Messenger"
        - "facebook_psid:XXXXX"
        """
        Partner = request.env['res.partner'].with_context(tracking_disable=True).sudo()
        
        # ✅ BƯỚC 1: Tìm customer cũ
        existing = self._find_existing_customer(conv.facebook_user_id)
        
        if existing:
            # ✅ CÓ CUSTOMER → Cập nhật thông tin nếu có thay đổi
            update_vals = {}
            
            if conv.customer_name and existing.name != conv.customer_name:
                update_vals['name'] = conv.customer_name
            
            if conv.customer_phone and existing.phone != conv.customer_phone:
                update_vals['phone'] = conv.customer_phone
            
            if conv.customer_address and existing.street != conv.customer_address:
                update_vals['street'] = conv.customer_address
            
            if update_vals:
                existing.write(update_vals)
                _logger.info(f"✅ Updated customer {existing.id}: {update_vals}")
            
            return existing
        
        else:
            # ✅ CHƯA CÓ → Tạo partner mới với 2 tag
            fb_tag = self._get_or_create_fb_messenger_tag()
            psid_tag = self._get_or_create_psid_tag(conv.facebook_user_id)
            
            partner = Partner.create({
                'name': conv.customer_name,
                'phone': conv.customer_phone,
                'street': conv.customer_address,
                'company_type': 'person',
                'category_id': [(6, 0, [fb_tag.id, psid_tag.id])],  # ✅ 2 TAG
            })
            
            _logger.info(f"✅ Created partner {partner.id} with 2 tags: {fb_tag.name}, {psid_tag.name}")
            
            return partner
    
    def _create_sale_order(self, conv, partner):
        """Tạo sale order"""
        SaleOrder = request.env['sale.order'].with_context(tracking_disable=True).sudo()
        
        order = SaleOrder.create({
            'partner_id': partner.id,
            'date_order': fields.Datetime.now(),
        })
        
        # Thêm products
        OrderLine = request.env['sale.order.line'].with_context(tracking_disable=True).sudo()
        
        quantity = conv.product_quantity or 1
        
        for product in conv.selected_product_ids:
            OrderLine.create({
                'order_id': order.id,
                'product_id': product.product_id.id,
                'product_uom_qty': quantity,
                'price_unit': product.price,
            })
        
        _logger.info(f"✅ Created sale order {order.name} (Total: {order.amount_total:,.0f})")
        
        return order
    
    # =========================================================================
    # ✅✅✅ HELPER: TẠO/CẬP NHẬT CRM LEAD (CỘNG DỒN REVENUE)
    # =========================================================================
    
    def _create_or_update_crm_lead(self, conv, partner, order):
        """
        ✅ YÊU CẦU 1 - TIÊU CHÍ 2
        
        Tạo/Cập nhật CRM Lead với logic:
        - Tìm lead cũ theo PSID tag
        - Nếu có → Cộng dồn expected_revenue (500000 + 1000000 = 1500000)
        - Nếu không → Tạo mới
        - Lead phải có 2 tag: "Facebook-Messenger" + "facebook_psid:XXXXX"
        """
        try:
            Lead = request.env['crm.lead'].with_context(tracking_disable=True).sudo()
            LeadTag = request.env['crm.tag'].sudo()
            
            # ✅ BƯỚC 1: Lấy 2 tag cho CRM Lead
            fb_tag = LeadTag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
            if not fb_tag:
                fb_tag = LeadTag.create({'name': 'Facebook-Messenger', 'color': 4})
            
            psid_tag_name = f"facebook_psid:{conv.facebook_user_id}"
            psid_tag = LeadTag.search([('name', '=', psid_tag_name)], limit=1)
            if not psid_tag:
                psid_tag = LeadTag.create({'name': psid_tag_name, 'color': 5})
            
            # ✅ BƯỚC 2: Tìm LEAD CŨ theo PSID tag
            existing_lead = Lead.search([
                ('tag_ids', 'in', [psid_tag.id]),
                ('partner_id', '=', partner.id),
            ], limit=1)
            
            if existing_lead:
                # ✅ CÓ LEAD CŨ → CỘNG DỒN REVENUE
                old_revenue = existing_lead.expected_revenue or 0
                new_revenue = old_revenue + order.amount_total
                
                existing_lead.write({
                    'expected_revenue': new_revenue,
                    'description': (existing_lead.description or '') + f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆕 ĐƠN HÀNG MỚI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Mã đơn: {order.name}
📅 Ngày: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
💰 Giá trị đơn: {order.amount_total:,.0f} đ
💵 Tổng tích lũy: {new_revenue:,.0f} đ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                })
                
                _logger.info(f"✅ Updated CRM Lead {existing_lead.name}: {old_revenue:,.0f} → {new_revenue:,.0f}")
                
                # Gắn lead vào conversation
                conv.sudo().write({'lead_id': existing_lead.id})
                
                return existing_lead
            
            else:
                # ✅ CHƯA CÓ → TẠO LEAD MỚI
                lead = Lead.create({
                    'name': f'FB Lead - {partner.name}',
                    'type': 'opportunity',
                    'partner_id': partner.id,
                    'contact_name': partner.name,
                    'phone': partner.phone,
                    'street': partner.street,
                    'expected_revenue': order.amount_total,
                    'tag_ids': [(6, 0, [fb_tag.id, psid_tag.id])],  # ✅ 2 TAG
                    'description': f"""Lead tạo từ Facebook Messenger Chatbot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 THÔNG TIN KHÁCH HÀNG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 Tên: {partner.name}
📞 SĐT: {partner.phone}
📍 Địa chỉ: {partner.street or 'Chưa có'}
🔑 PSID: {conv.facebook_user_id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 ĐƠN HÀNG ĐẦU TIÊN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Mã đơn: {order.name}
💰 Tổng tiền: {order.amount_total:,.0f} đ
📅 Ngày tạo: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
                })
                
                _logger.info(f"✅ Created CRM Lead: {lead.name} (Revenue: {order.amount_total:,.0f})")
                
                # Gắn lead vào conversation
                conv.sudo().write({'lead_id': lead.id})
                
                return lead
            
        except Exception as e:
            _logger.error(f'❌ Failed to create/update CRM Lead: {e}')
            import traceback
            _logger.error(traceback.format_exc())
            return None
    
    # =========================================================================
    # ✅✅✅ HELPER: SYNC SOCIAL.CONVERSATION
    # =========================================================================
    
    def _sync_to_conversation(self, conv, partner, lead):
        """
        ✅ YÊU CẦU 3
        
        Tạo/Cập nhật social.conversation:
        
        Trường hợp 1: Customer có (2 tag) + chưa nhắn tin
          → Tạo line mới
        
        Trường hợp 2: Customer có + đã nhắn tin + đã có line
          → Cập nhật line
        
        Trường hợp 3: Customer mới (chưa có 2 tag)
          → Tạo line mới
        """
        try:
            Conversation = request.env['social.conversation'].sudo()
            
            # ✅ BƯỚC 1: Tìm conversation hiện tại
            existing_conv = Conversation.search([
                ('facebook_psid', '=', conv.facebook_user_id),
                ('account_id', '=', conv.account_id.id),
            ], limit=1)
            
            conv_vals = {
                'customer_name': conv.customer_name,
                'customer_phone': conv.customer_phone,
                'last_message_date': fields.Datetime.now(),
                'state': 'ongoing',
                'lead_id': lead.id if lead else False,
            }
            
            if existing_conv:
                # ✅ TRƯỜNG HỢP 2: Đã có line → Cập nhật
                existing_conv.write(conv_vals)
                _logger.info(f"✅ Updated social.conversation {existing_conv.id}")
            else:
                # ✅ TRƯỜNG HỢP 1 & 3: Chưa có line → Tạo mới
                
                # Tạo conversation_id theo số thứ tự
                next_id = Conversation.search_count([]) + 1
                
                conv_vals.update({
                    'facebook_psid': conv.facebook_user_id,
                    'account_id': conv.account_id.id,
                    'company_id': conv.company_id.id,
                    'conversation_id': f"CONV-{next_id:05d}",
                })
                
                new_conv = Conversation.create(conv_vals)
                _logger.info(f"✅ Created social.conversation {new_conv.id} (ID: {new_conv.conversation_id})")
        
        except Exception as e:
            _logger.error(f"❌ Failed to sync conversation: {e}")
            import traceback
            _logger.error(traceback.format_exc())
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _handle_product_selection(self, conv, product_id):
        try:
            product = request.env['social.messenger.product'].sudo().browse(product_id)
            
            if not product.exists():
                self._send_text(conv, "❌ Sản phẩm không tồn tại!")
                return
            
            conv.sudo().write({
                'selected_product_ids': [(6, 0, [product.id])],
                'chatbot_state': 'ask_quantity'
            })
            
            ask_qty_msg = f"""✅ Bạn đã chọn: {product.product_id.name}

💰 Giá: {product.price:,.0f} đ

🔢 Bạn muốn mua bao nhiêu?
👉 Vui lòng nhập số lượng (VD: 1, 2, 5...)"""
            
            self._send_text(conv, ask_qty_msg)
            
        except Exception as e:
            _logger.error(f'❌ Product selection error: {e}')
    
    def _send_text(self, conv, text):
        """Gửi tin nhắn text qua Messenger"""
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': conv.facebook_user_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': conv.account_id.access_token}
        
        try:
            resp = requests.post(url, json=payload, params=params, timeout=10)
            if resp.status_code == 200:
                _logger.info(f"✅ Sent message to {conv.facebook_user_id}")
                return True
            else:
                _logger.error(f"❌ Failed to send message: {resp.text}")
                return False
        except Exception as e:
            _logger.error(f"❌ Send message error: {e}")
            return False
    
    def _send_product_list(self, conv):
        """Gửi danh sách sản phẩm với quick replies"""
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', conv.company_id.id)
        ], order='sequence, id')
        
        if not products:
            self._send_text(conv, "❌ Xin lỗi, hiện tại chưa có sản phẩm!")
            return
        
        product_list = "📦 DANH SÁCH SẢN PHẨM\n\n"
        
        for idx, p in enumerate(products, 1):
            price = f"{p.price:,.0f} đ" if p.price > 0 else "Liên hệ"
            product_list += f"{idx}. {p.product_id.name}\n   💰 {price}\n\n"
        
        product_list += "👇 Chọn sản phẩm bạn muốn mua:"
        
        quick_replies = []
        for p in products[:11]:  # Facebook limit 11 quick replies
            quick_replies.append({
                'content_type': 'text',
                'title': p.quick_reply_title or p.product_id.name[:20],
                'payload': f'PRODUCT_{p.id}'
            })
        
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': conv.facebook_user_id},
            'message': {
                'text': product_list,
                'quick_replies': quick_replies
            },
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': conv.account_id.access_token}
        
        try:
            resp = requests.post(url, json=payload, params=params, timeout=10)
            if resp.status_code == 200:
                _logger.info(f"✅ Sent product list to {conv.facebook_user_id}")
        except Exception as e:
            _logger.error(f"❌ Send product list error: {e}")
    
    def _validate_order_data(self, conv):
        """Validate dữ liệu đơn hàng"""
        errors = []
        
        if not conv.customer_name:
            errors.append("Thiếu tên")
        if not conv.customer_phone:
            errors.append("Thiếu SĐT")
        if not conv.customer_address:
            errors.append("Thiếu địa chỉ")
        if not conv.selected_product_ids:
            errors.append("Chưa chọn SP")
        if not hasattr(conv, 'product_quantity') or not conv.product_quantity:
            errors.append("Thiếu số lượng")
        
        return {
            'valid': len(errors) == 0,
            'errors': ', '.join(errors)
        }
    
    def _set_cooldown(self, conv):
        """
        ✅ SỬA: Giảm cooldown xuống 10 giây
        
        Mục đích: Tránh spam order liên tục
        """
        try:
            cooldown_until = datetime.now() + timedelta(seconds=10)  # ✅ 10 giây thay vì 1 phút
            conv.sudo().write({'cooldown_until': cooldown_until})
            _logger.info(f"✅ Set cooldown 10s for {conv.facebook_user_id}")
        except Exception as e:
            _logger.error(f"❌ Set cooldown error: {e}")
    
    def _is_in_cooldown(self, conv):
        """Kiểm tra có đang trong cooldown không"""
        if not hasattr(conv, 'cooldown_until') or not conv.cooldown_until:
            return False
        return conv.cooldown_until > datetime.now()
    
    def _extract_product_id(self, payload):
        """Lấy product ID từ payload"""
        try:
            return int(payload.replace('PRODUCT_', ''))
        except:
            return None
    
    def _find_or_create_conversation(self, sender_id, recipient_id):
        """Tìm hoặc tạo conversation (social.message)"""
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)
        ], limit=1)
        
        if not account:
            _logger.warning(f"⚠️ Account not found for page ID: {recipient_id}")
            return None
        
        conv = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', sender_id),
            ('account_id', '=', account.id),
        ], limit=1)
        
        if conv:
            _logger.info(f"✅ Found conversation for PSID: {sender_id}")
            return conv
        
        conv_vals = {
            'facebook_user_id': sender_id,
            'account_id': account.id,
            'company_id': account.company_id.id,
            'chatbot_state': 'idle',
        }
        
        try:
            new_conv = request.env['social.message'].sudo().create(conv_vals)
            _logger.info(f"✅ Created conversation for PSID: {sender_id}")
            return new_conv
        except Exception as e:
            _logger.error(f"❌ Failed to create conversation: {e}")
            return None