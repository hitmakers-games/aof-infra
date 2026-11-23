"""Check the rendered Jenkins Git environment against Git's URL matching."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('tofu') and shutil.which('git'), 'OpenTofu and Git required')
class GitProxyTests(unittest.TestCase):
    def test_only_github_https_uses_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = (MODULE / 'main.tf').read_text()
            (root / 'main.tf').write_text(source[:source.index('resource "kubernetes_namespace"')])
            shutil.copy(MODULE / 'variables.tf', root / 'variables.tf')
            for name in ['backend', 'charts', 'parameters', 'agents', 'content-manager']:
                (root / name).symlink_to(MODULE / name, target_is_directory=True)
            direct = subprocess.run(
                ['tofu', f'-chdir={root}', 'console', '-var=admin_password=test'],
                input='jsonencode(local.github_proxy_jcasc)\n', text=True,
                capture_output=True, check=True,
            )
            self.assertEqual(json.loads(json.loads(direct.stdout)), {})
            result = subprocess.run(
                ['tofu', f'-chdir={root}', 'console', '-var=admin_password=test',
                 '-var=github_proxy_url=http://aof-agent-vpn.aof-agent-network.svc.cluster.local:8888'],
                input='jsonencode(local.github_proxy_jcasc)\n', text=True,
                capture_output=True, check=True,
            )
            jcasc = json.loads(json.loads(result.stdout))
            settings = {entry['key']: entry['value']
                        for entry in jcasc['globalNodeProperties'][0]['envVars']['env']}
            environment = dict(PATH=os.environ['PATH'], GIT_CONFIG_NOSYSTEM='1',
                               GIT_CONFIG_GLOBAL='/dev/null', **settings)
            for url, proxied in [
                ('https://github.com/hitmakers-games/aof-back.git', True),
                ('https://github.com/hitmakers-games/aof-front.git', True),
                ('https://github.com/hitmakers-games/aof-content-manager.git', True),
                ('http://github.com/example/repo.git', False),
                ('https://github.com.example.invalid/repo.git', False),
                ('https://registry.example.invalid/repo.git', False),
                ('https://jenkins.jenkins.svc.cluster.local/', False),
            ]:
                with self.subTest(url=url):
                    match = subprocess.run(
                        ['git', 'config', '--get-urlmatch', 'http.proxy', url],
                        cwd=root, env=environment, text=True, capture_output=True,
                    )
                    self.assertEqual(match.returncode, 0 if proxied else 1)
                    self.assertEqual(match.stdout.strip(), settings['GIT_CONFIG_VALUE_0'] if proxied else '')


if __name__ == '__main__':
    unittest.main()
