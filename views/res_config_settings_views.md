<odoo>

    <record id="res_config_settings_view_form_social_facebook" model="ir.ui.view">
        <field name="name">res.config.settings.view.form.inherit.social.facebook</field>
        <field name="model">res.config.settings</field>
        <field name="inherit_id" ref="base.res_config_settings_view_form"/>
        <field name="arch" type="xml">
            <!-- FIX: Target vào sheet thay vì div[class='settings'] -->
            <xpath expr="//sheet" position="inside">
                
                <div class="app_settings_block" data_key="module_social_facebook" 
                     string="Facebook Integration">
                    <h2>Facebook Integration</h2>
                    
                    <!-- Webhook Configuration -->
                    <div class="row mt16 o_settings_container">
                        <div class="col-12 col-lg-6 o_setting_box">
                            <div class="o_setting_left_pane"></div>
                            <div class="o_setting_right_pane">
                                <span class="o_form_label">Webhook Configuration</span>
                                <div class="text-muted">
                                    Configure your Facebook webhook settings
                                </div>
                                <div class="content-group mt16">
                                    <div class="row">
                                        <label for="facebook_verify_token" 
                                               class="col-lg-3 o_light_label"/>
                                        <field name="facebook_verify_token" 
                                               placeholder="e.g., 16112005"/>
                                    </div>
                                    <div class="row mt8">
                                        <label string="Webhook URL" 
                                               class="col-lg-3 o_light_label"/>
                                        <field name="facebook_webhook_url" readonly="1"/>
                                        <button name="action_copy_webhook_url" 
                                                type="object" 
                                                string="Copy URL" 
                                                class="btn-link ml8"
                                                icon="fa-copy"/>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Ngrok Integration -->
                    <div class="row mt16 o_settings_container">
                        <div class="col-12 col-lg-6 o_setting_box">
                            <div class="o_setting_left_pane"></div>
                            <div class="o_setting_right_pane">
                                <span class="o_form_label">Ngrok Integration</span>
                                <div class="text-muted">
                                    Manage ngrok tunnel for localhost development
                                </div>
                                <div class="content-group mt16">
                                    <div class="row">
                                        <label for="ngrok_executable_path" 
                                               class="col-lg-3 o_light_label"/>
                                        <field name="ngrok_executable_path" 
                                               placeholder="C:/ngrok/ngrok.exe"/>
                                    </div>
                                    <div class="row mt8">
                                        <label string="Ngrok Status" 
                                               class="col-lg-3 o_light_label"/>
                                        <field name="ngrok_is_running" readonly="1" 
                                               widget="boolean"/>
                                        <span class="ml8" 
                                              invisible="not ngrok_is_running">
                                            ✅ Running
                                        </span>
                                        <span class="ml8 text-muted" 
                                              invisible="ngrok_is_running">
                                            ⛔ Not Running
                                        </span>
                                    </div>
                                    <div class="row mt8" 
                                         invisible="not ngrok_tunnel_url">
                                        <label string="Public URL" 
                                               class="col-lg-3 o_light_label"/>
                                        <field name="ngrok_tunnel_url" readonly="1" 
                                               class="text-primary font-weight-bold"/>
                                    </div>
                                    <div class="row mt16">
                                        <div class="col-lg-3"></div>
                                        <div>
                                            <button name="action_start_ngrok" 
                                                    type="object" 
                                                    string="Start Ngrok" 
                                                    class="btn-primary"
                                                    icon="fa-play"
                                                    invisible="ngrok_is_running"/>
                                            <button name="action_stop_ngrok" 
                                                    type="object" 
                                                    string="Stop Ngrok" 
                                                    class="btn-secondary ml8"
                                                    icon="fa-stop"
                                                    invisible="not ngrok_is_running"/>
                                            <button name="action_refresh_ngrok_url" 
                                                    type="object" 
                                                    string="Refresh" 
                                                    class="btn-link ml8"
                                                    icon="fa-refresh"/>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- CRM Integration -->
                    <div class="row mt16 o_settings_container">
                        <div class="col-12 col-lg-6 o_setting_box">
                            <div class="o_setting_left_pane">
                                <field name="auto_create_lead"/>
                            </div>
                            <div class="o_setting_right_pane">
                                <label for="auto_create_lead"/>
                                <div class="text-muted">
                                    Automatically create CRM leads from Messenger conversations
                                </div>
                                <div class="content-group mt16" 
                                     invisible="not auto_create_lead">
                                    <div class="row">
                                        <label for="lead_default_user_id" 
                                               string="Default Salesperson" 
                                               class="col-lg-3 o_light_label"/>
                                        <field name="lead_default_user_id"/>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Chatbot Configuration -->
                    <div class="row mt16 o_settings_container">
                        <div class="col-12 col-lg-6 o_setting_box">
                            <div class="o_setting_left_pane">
                                <field name="chatbot_enabled"/>
                            </div>
                            <div class="o_setting_right_pane">
                                <label for="chatbot_enabled"/>
                                <div class="text-muted">
                                    Enable automatic sales chatbot on Messenger
                                </div>
                                <div class="content-group mt16" 
                                     invisible="not chatbot_enabled">
                                    <div class="row">
                                        <label for="chatbot_welcome_message" 
                                               string="Welcome Message" 
                                               class="col-lg-3 o_light_label"/>
                                        <field name="chatbot_welcome_message" 
                                               widget="text"/>
                                    </div>
                                    <div class="alert alert-info mt16" role="alert">
                                        <strong>Chatbot Flow:</strong><br/>
                                        1. Ask customer name<br/>
                                        2. Ask phone number<br/>
                                        3. Show product catalog<br/>
                                        4. Confirm order<br/>
                                        5. Create sale order automatically
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                </div>
                
            </xpath>
        </field>
    </record>

</odoo>