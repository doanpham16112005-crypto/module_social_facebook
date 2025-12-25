/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Custom List Controller for Social Conversation
 * Adds "Sync All Conversations" button to the toolbar
 */
export class SocialConversationListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
    }

    /**
     * Handler for Sync All Conversations button
     */
    async onClickSyncConversations() {
        // Show loading notification
        this.notification.add("Đang đồng bộ conversations từ Facebook...", {
            type: "info",
        });

        try {
            // Call the server method
            const result = await this.orm.call(
                "social.conversation",
                "action_sync_all_conversations",
                [[]]
            );

            // Reload the list view
            await this.model.load();

            // Show success notification
            if (result && result.params) {
                this.notification.add(result.params.message, {
                    type: result.params.type || "success",
                    sticky: result.params.sticky || false,
                });
            } else {
                this.notification.add("Đồng bộ hoàn tất!", {
                    type: "success",
                });
            }
        } catch (error) {
            console.error("Error syncing conversations:", error);
            this.notification.add("Lỗi khi đồng bộ: " + (error.message || error), {
                type: "danger",
                sticky: true,
            });
        }
    }
}

// Define the template with the sync button
SocialConversationListController.template = "module_social_facebook.SocialConversationListView";

// Create custom list view for social.conversation
export const SocialConversationListView = {
    ...listView,
    Controller: SocialConversationListController,
    buttonTemplate: "module_social_facebook.SocialConversationListView.Buttons",
};

// Register the view
registry.category("views").add("social_conversation_list", SocialConversationListView);