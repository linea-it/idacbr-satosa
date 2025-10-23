"""
OAuth backend for Github Org Custom
"""
import json
import logging
import requests
from oic.oauth2.message import AuthorizationResponse
from satosa.backends.github import GitHubBackend
from satosa.internal import InternalData
from satosa.exception import SATOSAAuthenticationError

logger = logging.getLogger(__name__)
handler = logging.FileHandler('/tmp/pipeline.log')
formatter = logging.Formatter(
    '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


class GitHubOrgBackend(GitHubBackend):
    """GitHub OAuth 2.0 backend for organization"""

    def __init__(self, outgoing, internal_attributes, config, base_url, name):
        """GitHub backend constructor
        :param outgoing: Callback should be called by the module after the
            authorization in the backend is done.
        :param internal_attributes: Mapping dictionary between SATOSA internal
            attribute names and the names returned by underlying IdP's/OP's as
            well as what attributes the calling SP's and RP's expects namevice.
        :param config: configuration parameters for the module.
        :param base_url: base url of the service
        :param name: name of the plugin
        :type outgoing:
            (satosa.context.Context, satosa.internal.InternalData) ->
            satosa.response.Response
        :type internal_attributes: dict[string, dict[str, str | list[str]]]
        :type config: dict[str, dict[str, str] | list[str] | str]
        :type base_url: str
        :type name: str
        """
        config.setdefault('response_type', 'code')
        config['verify_accesstoken_state'] = False
        super().__init__(outgoing, internal_attributes, config, base_url, name)

    def _authn_response(self, context):
        state_data = context.state[self.name]
        aresp = self.consumer.parse_response(
            AuthorizationResponse, info=json.dumps(context.request))
        self._verify_state(aresp, state_data, context.state)
        url = self.config['server_info']['token_endpoint']
        data = dict(
            code=aresp['code'],
            redirect_uri=self.redirect_url,
            client_id=self.config['client_config']['client_id'],
            client_secret=self.config['client_secret'], )
        headers = {'Accept': 'application/json'}

        r = requests.post(url, data=data, headers=headers)
        response = r.json()
        if self.config.get('verify_accesstoken_state', True):
            self._verify_state(response, state_data, context.state)

        user_info = self.user_information(response["access_token"])

        org_and_team = self.check_org_and_team(
            user_info.get("login"), response["access_token"]
        )

        logger.info('--> org and team')
        logger.info(org_and_team)

        if not org_and_team.get('ok'):
            logger.info("error 01")
            raise SATOSAAuthenticationError(
                context.state,
                "User is not part of org %s and(or) team %s" % (
                    self.config['server_info']['org'],
                    self.config['server_info']['team']
                )
            )
        elif org_and_team.get('state') != "active":
            logger.info("error 02")
            raise SATOSAAuthenticationError(
                context.state,
                "User state is '%s' in %s team, only user with \
                    'active' state will be accepted." % (
                        org_and_team.get('state'),
                        self.config['server_info']['team']
                    )
            )

        auth_info = self.auth_info(context.request)
        internal_response = InternalData(auth_info=auth_info)
        internal_response.attributes = self.converter.to_internal(
            self.external_type, user_info)
        internal_response.subject_id = str(user_info[self.user_id_attr])
        del context.state[self.name]
        return self.auth_callback_func(context, internal_response)

    def check_org_and_team(self, username, access_token):
        """ Checks if the user is part of the organization and team 
        configured in the backend yaml file.
        :param username: github login
        :param access_token: github token
        :type username: str
        :type access_token: str
        """
        url = self.config['server_info']['check_org_team']
        url = url.format(
            org=self.config['server_info']['org'],
            team=self.config['server_info']['team'],
            username=username
        )
        logger.info('->> URL')
        logger.info(url)
        headers = {'Authorization': 'token {}'.format(access_token)}
        logger.info(f"->> TOKEN: {access_token}")
        r = requests.get(url, headers=headers)
        ret = r.json()
        ret['ok'] = r.ok
        ret['state'] = ret.get("state", "not found")
        return ret
        
