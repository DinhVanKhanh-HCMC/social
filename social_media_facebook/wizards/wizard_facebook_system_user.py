import logging
from datetime import datetime, timedelta

from odoo import fields, models
from odoo.exceptions import ValidationError

from ..social_facebook_utils import _URL_GRAPH_FACEBOOK

_logger = logging.getLogger(__name__)


class WizardFacebookSystemUser(models.TransientModel):
    _name = "wizard.facebook.system.user"
    _description = "Wizard for entering system user token"

    system_user_token = fields.Char()
    page_ids = fields.One2many(
        "wizard.facebook.system.user.line",
        "wizard_id",
        string="Select Pages",
        help="Select the Facebook pages you want to connect",
    )
    ad_account_ids = fields.One2many(
        "wizard.facebook.system.user.ad.account",
        "wizard_id",
        string="Available Ad Accounts",
        help="Ad accounts available for selection",
    )
    state = fields.Selection(
        [("token", "Enter Token"), ("pages", "Select Pages")],
        default="token",
    )

    def action_fetch_pages(self):
        """Validate token and fetch pages and ad accounts"""
        token = self.system_user_token
        if not token:
            raise ValidationError(self.env._("System User Token is required"))

        try:
            import requests

            r = requests.get(
                f"{_URL_GRAPH_FACEBOOK}/me", params={"access_token": token}, timeout=8
            )
            r.raise_for_status()
        except Exception as e:
            _logger.error(f"Error validating system user token: {e}")
            raise ValidationError(
                self.env._("Invalid System User Token or network error.")
            ) from e

        # Fetch pages
        pages = []
        try:
            pages = get_pages_from_facebook(token)
        except Exception as e:
            raise ValidationError(
                self.env._(
                    "Failed to fetch pages using the provided System User Token."
                )
            ) from e

        if not pages:
            raise ValidationError(
                self.env._(
                    "No Facebook pages found for the provided System User Token."
                )
            )

        # Fetch ad accounts
        _logger.debug("Fetching available Facebook ad accounts...")
        ad_accounts = self.env["social.account"].get_ad_accounts_facebook(token)
        _logger.debug(f"Found {len(ad_accounts)} ad accounts")

        # safe get media reference
        media_ref = self.env.ref(
            "social_media_facebook.social_media_facebook", raise_if_not_found=False
        )
        media_id = media_ref.id if media_ref else False

        # Create ad account lines
        for ad_account in ad_accounts:
            self.env["wizard.facebook.system.user.ad.account"].create(
                {
                    "wizard_id": self.id,
                    "ad_account_id": ad_account.get("id", ""),
                    "ad_account_name": ad_account.get("name", ""),
                    "account_status": ad_account.get("account_status", 0),
                    "currency": ad_account.get("currency", ""),
                }
            )
            _logger.debug(
                f"Created ad account line for {ad_account.get('name')} "
                f"(ID: {ad_account.get('id')})"
            )

        # Create page lines
        for page in pages:
            page_id = page.get("id")
            page_name = page.get("name")

            # Check if page already connected
            already_connected = bool(
                self.env["social.account"].search(
                    [
                        ("page_id", "=", page_id),
                        ("media_id", "=", media_id),
                    ],
                    limit=1,
                )
            )

            self.env["wizard.facebook.system.user.line"].create(
                {
                    "wizard_id": self.id,
                    "page_id": page_id,
                    "page_name": page_name,
                    "page_access_token": page.get("access_token") or token,
                    "selected": not already_connected,
                    "already_connected": already_connected,
                }
            )
            _logger.debug(
                f"Created page line for {page_name} (ID: {page_id}), "
                f"selected: {not already_connected}"
            )

        # Move to page selection state
        self.state = "pages"

        # Return action to reload the wizard in page selection view
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.facebook.system.user",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_connect_system_user(self):
        """Connect selected pages using the System User token"""
        token = self.system_user_token
        if not token:
            raise ValidationError(self.env._("System User Token is required"))

        selected_pages = self.page_ids.filtered(lambda p: p.selected)
        _logger.debug(f"Selected pages count: {len(selected_pages)}")

        if not selected_pages:
            raise ValidationError(
                self.env._("Please select at least one page to connect.")
            )

        created = []
        updated = []
        failed = []

        # safe get media reference
        media_ref = self.env.ref(
            "social_media_facebook.social_media_facebook", raise_if_not_found=False
        )
        media_id = media_ref.id if media_ref else False

        token_expires_at = datetime.now() + timedelta(days=365 * 10)

        for line in selected_pages:
            page_id = line.page_id
            page_name = line.page_name
            page_token = line.page_access_token
            ad_account_id = (
                line.ad_account_id.ad_account_id if line.ad_account_id else False
            )

            try:
                with self.env.cr.savepoint():
                    exiting = self.env["social.account"].search(
                        [
                            ("page_id", "=", page_id),
                            ("media_id", "=", media_id),
                        ],
                        limit=1,
                    )

                    vals = {
                        "name": page_name,
                        "username": page_name,
                        "page_id": page_id,
                        "page_name": page_name,
                        "page_access_token": page_token,
                        "facebook_user_token": token,
                        "access_token": page_token,
                        "token_expires_at": token_expires_at,
                        "status": "active",
                        "media_id": media_id,
                    }

                    # Add ad account ID if selected
                    if ad_account_id:
                        vals["fb_ad_account_id"] = ad_account_id
                        _logger.debug(
                            f"Assigning ad account {ad_account_id} to page {page_name}"
                        )

                    try:
                        pic = self.env[
                            "social.account"
                        ]._download_facebook_page_picture(page_id, page_token)
                        if pic:
                            vals["image_1920"] = pic
                    except Exception as e:
                        _logger.warning(
                            f"Failed to download profile picture for page {page_name} "
                            f"(ID: {page_id}): {e}"
                        )

                    if token:
                        vals["facebook_system_user_token"] = token
                        vals["facebook_app_id"] = False
                        vals["facebook_app_secret"] = False

                    if exiting:
                        exiting.write(vals)
                        updated.append(exiting.id)
                    else:
                        new = self.env["social.account"].create(vals)
                        created.append(new.id)
            except Exception as e:
                _logger.error(
                    f"Failed to create/update account for page {page_name} "
                    f"(ID: {page_id}): {e}"
                )
                failed.append({"page_id": page_id, "error": str(e)})

        try:
            key = "social_media_base.facebook_system_user_token"
            self.env["ir.config_parameter"].sudo().set_param(key, token)
            self.env["ir.config_parameter"].sudo().set_param(
                "social_media_base.facebook_connection_method", "system_user"
            )
        except Exception as e:
            _logger.error(f"Failed to save system user token to config parameters: {e}")

        if failed:
            msg = self.env._(
                f"Created: {len(created)}, Updated: {len(updated)}, "
                f"Failed: {len(failed)} accounts."
            )
            raise ValidationError(msg)

        # Return action to show created accounts
        return {
            "type": "ir.actions.act_window",
            "name": "Facebook Accounts",
            "res_model": "social.account",
            "view_mode": "list,form",
            "domain": [("media_type", "=", "facebook")],
            "context": {
                "search_default_filter_facebook": 1,
            },
            "target": "current",
        }


class WizardFacebookSystemUserLine(models.TransientModel):
    _name = "wizard.facebook.system.user.line"
    _description = "Facebook Page Selection Line (System User)"

    wizard_id = fields.Many2one(
        "wizard.facebook.system.user",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    page_id = fields.Char(string="Page ID", required=True)
    page_name = fields.Char(required=True)
    page_access_token = fields.Char(required=True)
    selected = fields.Boolean(string="Select", default=True)
    already_connected = fields.Boolean(readonly=True)
    ad_account_id = fields.Many2one(
        "wizard.facebook.system.user.ad.account",
        string="Ad Account",
        domain="[('wizard_id', '=', wizard_id)]",
        help="Select an advertising account to link with this page",
    )


class WizardFacebookSystemUserAdAccount(models.TransientModel):
    _name = "wizard.facebook.system.user.ad.account"
    _description = "Facebook Ad Account Selection (System User)"
    _rec_name = "ad_account_name"

    wizard_id = fields.Many2one(
        "wizard.facebook.system.user",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    ad_account_id = fields.Char(string="Ad Account ID", required=True)
    ad_account_name = fields.Char(string="Name", required=True)
    account_status = fields.Integer(string="Status")
    currency = fields.Char()

    def name_get(self):
        """Display ad account name with ID"""
        result = []
        for record in self:
            name = f"{record.ad_account_name} ({record.ad_account_id})"
            result.append((record.id, name))
        return result


def get_pages_from_facebook(system_user_token):
    """Fetch pages using the system user token from Facebook API"""
    import requests
    from requests.adapters import HTTPAdapter, Retry

    url = f"{_URL_GRAPH_FACEBOOK}/me/accounts"
    params = {
        "access_token": system_user_token,
    }
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))

    try:
        response = session.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        _logger.error(f"Error fetching pages from Facebook: {e}")
        raise

    pages = []
    for p in data.get("data", []):
        pages.append(
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "access_token": p.get("access_token"),
            }
        )
    return pages
