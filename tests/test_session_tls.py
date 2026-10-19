import os
import unittest
from unittest.mock import patch

from requests import Response
from requests.exceptions import SSLError

from startlive.core import app_state
from startlive.core.constant import HeadersType, ProxyMode


class SessionTlsTests(unittest.TestCase):
    def setUp(self):
        saved_settings = app_state.app_settings.as_dict()
        self.addCleanup(app_state.app_settings.update, saved_settings)
        environment = patch.dict(os.environ, {
            "HTTP_PROXY": "http://system-proxy.invalid:8080",
            "HTTPS_PROXY": "http://system-proxy.invalid:8080",
            "REQUESTS_CA_BUNDLE": "/fixture/environment-ca.pem",
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def session(self, mode, headers=HeadersType.WEB):
        app_state.app_settings.update({
            "proxy_mode": mode,
            "custom_proxy_url": "http://custom-proxy.invalid:8081",
        })
        session = app_state.create_session(headers, inherit_account_cookies=False)
        self.addCleanup(session.close)
        return session

    def test_proxy_modes_keep_verification_routing_and_timeouts(self):
        for mode in (ProxyMode.NONE, ProxyMode.SYSTEM, ProxyMode.CUSTOM):
            for headers in (HeadersType.WEB, HeadersType.APP):
                for method in ("get", "post"):
                    with self.subTest(mode=mode, headers=headers, method=method):
                        session = self.session(mode, headers)
                        with patch.object(session, "send", return_value=Response()) as send:
                            getattr(session, method)("https://api.bilibili.com/fixture")
                        options = send.call_args.kwargs
                        expected_verify = ("/fixture/environment-ca.pem"
                                           if mode == ProxyMode.SYSTEM else True)
                        self.assertEqual(options["verify"], expected_verify)
                        self.assertEqual(options["timeout"], 5)
                        self.assertEqual(session.trust_env, mode == ProxyMode.SYSTEM)
                        proxy = {
                            ProxyMode.NONE: None,
                            ProxyMode.SYSTEM: "http://system-proxy.invalid:8080",
                            ProxyMode.CUSTOM: "http://custom-proxy.invalid:8081",
                        }[mode]
                        expected_proxies = {} if proxy is None else {
                            "http": proxy, "https": proxy,
                        }
                        self.assertEqual(dict(options["proxies"]), expected_proxies)

    def test_explicit_ca_bundle_remains_supported_in_every_mode(self):
        for mode in (ProxyMode.NONE, ProxyMode.SYSTEM, ProxyMode.CUSTOM):
            for method in ("get", "post"):
                with self.subTest(mode=mode, method=method):
                    session = self.session(mode)
                    with patch.object(session, "send", return_value=Response()) as send:
                        getattr(session, method)("https://api.bilibili.com/fixture",
                                                 verify="/fixture/explicit-ca.pem")
                    self.assertEqual(send.call_args.kwargs["verify"],
                                     "/fixture/explicit-ca.pem")

    def test_certificate_errors_propagate_without_an_insecure_retry(self):
        for mode in (ProxyMode.SYSTEM, ProxyMode.CUSTOM):
            for method in ("get", "post"):
                with self.subTest(mode=mode, method=method):
                    session = self.session(mode)
                    with patch.object(session, "send", side_effect=SSLError("fixture")) as send:
                        with self.assertRaises(SSLError):
                            getattr(session, method)("https://api.bilibili.com/fixture")
                    self.assertEqual(send.call_count, 1)
