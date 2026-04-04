import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(
  defineConfig({
    title: 'uv-release',
    description: 'Release management for uv workspaces',
    srcExclude: ['adr/**'],

    themeConfig: {
      nav: [
        {
          text: 'User Guide',
          items: [
            {
              text: 'Getting Started',
              items: [
                { text: 'Setup', link: '/user-guide/01-setup' },
                { text: 'Upgrading', link: '/user-guide/10b-upgrading' },
              ],
            },
            {
              text: 'Workflow',
              items: [
                { text: 'Status', link: '/user-guide/02-status' },
                { text: 'Bump', link: '/user-guide/03-bumping' },
                { text: 'Build', link: '/user-guide/04-building' },
                { text: 'Release', link: '/user-guide/05-releasing' },
                { text: 'Release with Claude', link: '/user-guide/05b-claude' },
              ],
            },
            {
              text: 'Configuration',
              items: [
                { text: 'Overview', link: '/user-guide/13-configuration' },
                { text: 'Filtering', link: '/user-guide/06-filtering' },
                { text: 'Runners', link: '/user-guide/07-runners' },
                { text: 'Custom Jobs', link: '/user-guide/08-custom-jobs' },
                { text: 'Python Hooks', link: '/user-guide/09-python-hooks' },
              ],
            },
            {
              text: 'More',
              items: [
                { text: 'Installing', link: '/user-guide/10-installing' },
                { text: 'Troubleshooting', link: '/user-guide/11-troubleshooting' },
                { text: 'Command Reference', link: '/user-guide/12-commands' },
              ],
            },
          ],
        },
        {
          text: 'Under the Hood',
          items: [
            { text: 'Architecture', link: '/under-the-hood/08-architecture' },
            { text: 'Init & Validation', link: '/under-the-hood/01-init-and-validation' },
            { text: 'Change Detection', link: '/under-the-hood/02-change-detection' },
            { text: 'Dependency Pinning', link: '/under-the-hood/03-dependency-pinning' },
            { text: 'Build Matrix', link: '/under-the-hood/04-build-matrix' },
            { text: 'Workflow Model', link: '/under-the-hood/05-workflow-model' },
            { text: 'Release Plan', link: '/under-the-hood/06-release-plan' },
            { text: 'CI Execution', link: '/under-the-hood/07-ci-execution' },
            { text: 'Architecture', link: '/under-the-hood/08-architecture' },
          ],
        },
        { text: 'Changelog', link: '/CHANGELOG' },
      ],

      sidebar: {
        '/user-guide/': [
          {
            text: 'Getting Started',
            items: [
              { text: 'Setup', link: '/user-guide/01-setup' },
              { text: 'Upgrading', link: '/user-guide/10b-upgrading' },
            ],
          },
          {
            text: 'Workflow',
            items: [
              { text: 'Status', link: '/user-guide/02-status' },
              { text: 'Bump', link: '/user-guide/03-bumping' },
              { text: 'Build', link: '/user-guide/04-building' },
              { text: 'Release', link: '/user-guide/05-releasing' },
              { text: 'Release with Claude', link: '/user-guide/05b-claude' },
            ],
          },
          {
            text: 'Configuration',
            collapsed: false,
            items: [
              { text: 'Overview', link: '/user-guide/13-configuration' },
              { text: 'Filtering', link: '/user-guide/06-filtering' },
              { text: 'Runners', link: '/user-guide/07-runners' },
              { text: 'Custom Jobs', link: '/user-guide/08-custom-jobs' },
              { text: 'Python Hooks', link: '/user-guide/09-python-hooks' },
            ],
          },
          {
            text: 'More',
            items: [
              { text: 'Installing', link: '/user-guide/10-installing' },
              { text: 'Troubleshooting', link: '/user-guide/11-troubleshooting' },
              { text: 'Command Reference', link: '/user-guide/12-commands' },
            ],
          },
        ],
        '/under-the-hood/': [
          {
            text: 'Under the Hood',
            items: [
              { text: 'Architecture', link: '/under-the-hood/08-architecture' },
              { text: 'Init & Validation', link: '/under-the-hood/01-init-and-validation' },
              { text: 'Change Detection', link: '/under-the-hood/02-change-detection' },
              { text: 'Dependency Pinning', link: '/under-the-hood/03-dependency-pinning' },
              { text: 'Build Matrix', link: '/under-the-hood/04-build-matrix' },
              { text: 'Workflow Model', link: '/under-the-hood/05-workflow-model' },
              { text: 'Release Plan', link: '/under-the-hood/06-release-plan' },
              { text: 'CI Execution', link: '/under-the-hood/07-ci-execution' },
              { text: 'Architecture', link: '/under-the-hood/08-architecture' },
            ],
          },
        ],
      },

      socialLinks: [
        { icon: 'github', link: 'https://github.com/tylerpayne/lazy-wheels' },
      ],

      search: {
        provider: 'local',
      },

      editLink: {
        pattern: 'https://github.com/tylerpayne/lazy-wheels/edit/main/docs/:path',
      },
    },

    mermaid: {},
  })
)
