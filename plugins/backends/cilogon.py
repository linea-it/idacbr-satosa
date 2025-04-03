import logging
from satosa.backends.openid_connect import OpenIDConnectBackend
from datetime import datetime, timezone
from oic.utils import time_util

logger = logging.getLogger(__name__)


class OpenIDConnectCustomBackend(OpenIDConnectBackend):
    """
    A custom OpenID Connect backend that extends the base OpenIDConnectBackend with specific token retrieval logic.
    
    This backend handles token retrieval for OpenID Connect authentication, with support for custom response type skew
    and detailed token request processing.
    """

    def _get_tokens(self, authn_response, context):
        """
        :param authn_response: authentication response from OP
        :type authn_response: oic.oic.message.AuthorizationResponse
        :return: access token and ID Token claims
        :rtype: Tuple[Optional[str], Optional[Mapping[str, str]]]
        """

        skew = self.config.get("auth_req_params", {}).get("skew", 0)

        logger.debug('Custom skew: %s', skew)

        if "code" in authn_response:
            # make token request
            args = {
                "code": authn_response["code"],
                "redirect_uri": self.client.registration_response['redirect_uris'][0],
            }

            token_resp = self.client.do_access_token_request(scope="openid", state=authn_response["state"],
                                                             request_args=args,
                                                             authn_method=self.client.registration_response[
                                                                 "token_endpoint_auth_method"],
                                                             skew=skew)

            logger.debug('EXP date: %s', str(datetime.fromtimestamp(token_resp['exp'], tz=timezone.utc)))
            logger.debug('IAT date: %s', str(datetime.fromtimestamp(token_resp['iat'], tz=timezone.utc)))
            logger.debug('Now date: %s', str(datetime.fromtimestamp(time_util.utc_time_sans_frac(), tz=timezone.utc)))

            self._check_error_response(token_resp, context)
            return token_resp["access_token"], token_resp["id_token"]
