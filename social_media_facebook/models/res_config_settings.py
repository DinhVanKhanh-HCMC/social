# Copyright 2025 Kencove (https://www.kencove.com/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # === Facebook App Credentials ===
    facebook_app_id = fields.Char(
        string="App ID",
        config_parameter="social_media_base.facebook_app_id",
        help="Facebook App ID for OAuth authentication. Get this from https://developers.facebook.com/apps/",
    )
    facebook_app_secret = fields.Char(
        string="App Secret",
        config_parameter="social_media_base.facebook_app_secret",
        help="Facebook App Secret for OAuth authentication. Keep this confidential!",
    )
    facebook_redirect_uri = fields.Char(
        string="OAuth Redirect URI",
        compute="_compute_facebook_redirect_uri",
        readonly=True,
        help="Copy this URL to your Facebook App Settings → Products → Facebook Login → Valid OAuth Redirect URIs",
    )
    
    # === Facebook system user token ===
    facebook_system_user_token = fields.Char(
        string="System User Token",
        config_parameter="social_media_base.facebook_system_user_token",
    )
    
    def action_open_system_user_token_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": "System User Token",
            "res_model": "wizard.facebook.system.user",
            "view_mode": "form",
            "target": "new",
        }

    # === Facebook Lead Ads Webhook ===
    facebook_webhook_verify_token = fields.Char(
        string="Webhook Verify Token",
        config_parameter="social_media_facebook.webhook_verify_token",
        help="Custom token for verifying webhook requests from Facebook. Use a secure random string.",
        default="odoo_facebook_webhook",
    )
    facebook_webhook_url = fields.Char(
        string="Webhook URL",
        compute="_compute_facebook_webhook_url",
        readonly=True,
        help="Copy this URL to your Facebook App Settings → Webhooks → Callback URL",
    )

    def _compute_facebook_redirect_uri(self):
        """Compute the OAuth redirect URI for Facebook"""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for record in self:
            record.facebook_redirect_uri = f"{base_url}/facebook/callback"

    def _compute_facebook_webhook_url(self):
        """Compute the webhook URL for Facebook Lead Ads"""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for record in self:
            record.facebook_webhook_url = f"{base_url}/facebook/webhook/leads"
