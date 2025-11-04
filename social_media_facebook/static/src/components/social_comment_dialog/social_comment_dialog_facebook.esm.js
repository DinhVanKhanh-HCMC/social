/** @odoo-module **/

import {SocialCommentDialog} from "@social_media_base/components/social_comment_dialog/social_comment_dialog.esm";
import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";
import {onWillStart} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";

patch(SocialCommentDialog.prototype, {
    setup() {
        super.setup();
        this.socialFacebookService = useService("social_facebook_service");

        // Auto-sync comments when dialog opens (Facebook only)
        if (this.props.media_type.raw_value === "facebook") {
            onWillStart(async () => {
                await this.syncCommentsFromFacebook();
            });
        }
    },

    /**
     * Sync comments from Facebook for this post.
     *
     * This method calls the backend to fetch comments from Facebook
     * and store them in the database, then reloads the comment list.
     */
    async syncCommentsFromFacebook() {
        // Only sync for Facebook posts
        if (this.props.media_type.raw_value !== "facebook") {
            return;
        }

        try {
            // The props.post is a social.post.account record
            // We can use its ID directly
            const postAccountId = this.props.post.id.raw_value;

            console.log("=== DEBUG: Syncing Comments ===");
            console.log("Post Account ID:", postAccountId);
            console.log("Account ID:", this.props.account.raw_value);

            if (!postAccountId) {
                console.error("No post account ID found");
                this.notificationService.add(
                    _t("Unable to find post account ID"),
                    {type: "warning"}
                );
                return;
            }

            const result = await this.socialFacebookService.syncCommentsForPost(
                this.props.account.raw_value,
                postAccountId
            );

            console.log("Sync result:", result);

            if (result && result.success) {
                // Reload comments after sync
                await this.updateListComments();

                // Only show notification if we synced new comments
                if (result.comments_synced > 0) {
                    this.notificationService.add(
                        result.message || _t("Comments synced successfully"),
                        {type: "success"}
                    );
                }
            } else if (result && !result.success && result.message !== "No comments found on Facebook") {
                // Show error with the actual message from backend
                console.error("Sync failed:", result.message);
                this.notificationService.add(
                    result.message || _t("Failed to sync comments"),
                    {type: "warning"}
                );
            }
        } catch (error) {
            console.error("Error syncing Facebook comments:", error);
            this.notificationService.add(
                _t("An error occurred while syncing comments"),
                {type: "danger"}
            );
        }
    },

    /**
     * Send a new comment to Facebook
     *
     * Posts a new parent comment to the Facebook post
     */
    async _sendNewComment(message) {
        // Only handle Facebook posts
        if (this.props.media_type.raw_value !== "facebook") {
            return super._sendNewComment(message);
        }

        try {
            const result = await this.socialFacebookService.postNewComment(
                this.props.account.raw_value,
                this.props.post.id.raw_value,
                message
            );

            if (result && result.success) {
                return {
                    success: true,
                    message: result.message || "Comment posted successfully",
                };
            } else {
                return {
                    success: false,
                    message: result.message || "Failed to post comment",
                };
            }
        } catch (error) {
            console.error("Error posting Facebook comment:", error);
            return {
                success: false,
                message: "An error occurred while posting the comment",
            };
        }
    },
});
