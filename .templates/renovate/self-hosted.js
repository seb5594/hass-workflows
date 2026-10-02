// Global configuration for the self-hosted Renovate server.
// Secrets come from the environment: RENOVATE_TOKEN (GitHub PAT) and GITHUB_COM_TOKEN.
module.exports = {
  platform: 'github',
  gitAuthor: 'renovate-seb5594 <seb5594@users.noreply.github.com>',
  // Only repositories that carry their own renovate.json are processed.
  onboarding: false,
  requireConfig: 'required',
  autodiscover: false,
  repositories: [
    'seb5594/hass-workflows',
    'seb5594/Home-Assistant-Apps',
    'seb5594/Home-Assistant-git-exporter-Addon',
    'seb5594/Home-Assistant-Rsync-Local-Addon',
    'seb5594/hass-ninebot_e_scooters-integration',
  ],
  prHourlyLimit: 4,
  prConcurrentLimit: 6,
};
