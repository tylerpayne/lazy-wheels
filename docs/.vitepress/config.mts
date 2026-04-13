import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(
  defineConfig({
    title: 'uvr',
    description: 'Release management for uv workspaces',
    base: '/uvr/',
    srcExclude: ['adr/**'],
    head: [['link', { rel: 'icon', type: 'image/svg+xml', href: '/uvr/favicon.svg' }]],

    themeConfig: {
      nav: [
        {
          text: 'User Guide',
          items: [
            { text: 'Getting Started', link: '/user-guide/01-getting-started' },
            { text: 'Releasing', link: '/user-guide/02-releasing' },
            { text: 'Release with Claude', link: '/user-guide/03-claude' },
            { text: 'Versions', link: '/user-guide/04-versions' },
            { text: 'Configuration', link: '/user-guide/05-configuration' },
            { text: 'Customization', link: '/user-guide/06-customization' },
            { text: 'Troubleshooting', link: '/user-guide/07-troubleshooting' },
            { text: 'Reference', link: '/user-guide/08-reference' },
          ],
        },
        {
          text: 'Under the Hood',
          items: [
            { text: 'Architecture', link: '/under-the-hood/architecture' },
            { text: 'Change Detection', link: '/under-the-hood/01-change-detection' },
            { text: 'Bump', link: '/under-the-hood/02-bump' },
            { text: 'Build', link: '/under-the-hood/03-build' },
            { text: 'Workflow', link: '/under-the-hood/04-workflow' },
            { text: 'Release', link: '/under-the-hood/05-release' },
            { text: 'Package States', link: '/under-the-hood/package-states' },
          ],
        },
        { text: 'Changelog', link: '/CHANGELOG' },
      ],

      sidebar: {
        '/user-guide/': [
          {
            text: 'User Guide',
            items: [
              { text: 'Getting Started', link: '/user-guide/01-getting-started' },
              { text: 'Releasing', link: '/user-guide/02-releasing' },
              { text: 'Release with Claude', link: '/user-guide/03-claude' },
              { text: 'Versions', link: '/user-guide/04-versions' },
              { text: 'Configuration', link: '/user-guide/05-configuration' },
              { text: 'Customization', link: '/user-guide/06-customization' },
              { text: 'Troubleshooting', link: '/user-guide/07-troubleshooting' },
              { text: 'Reference', link: '/user-guide/08-reference' },
            ],
          },
        ],
        '/under-the-hood/': [
          {
            text: 'Under the Hood',
            items: [
              { text: 'Architecture', link: '/under-the-hood/architecture' },
              { text: 'Change Detection', link: '/under-the-hood/01-change-detection' },
              { text: 'Bump', link: '/under-the-hood/02-bump' },
              { text: 'Build', link: '/under-the-hood/03-build' },
              { text: 'Workflow', link: '/under-the-hood/04-workflow' },
              { text: 'Release', link: '/under-the-hood/05-release' },
              { text: 'Package States', link: '/under-the-hood/package-states' },
            ],
          },
        ],
      },

      socialLinks: [
        { icon: 'github', link: 'https://github.com/tylerpayne/uvr' },
      ],

      search: {
        provider: 'local',
      },

      editLink: {
        pattern: 'https://github.com/tylerpayne/uvr/edit/main/docs/:path',
      },
    },

    mermaid: {},
  })
)
