module.exports = {
  title: 'Document Search Platform',
  tagline: 'Intelligent document retrieval',
  url: 'https://docs.example.com',
  baseUrl: '/',
  onBrokenLinks: 'warn',
  favicon: 'img/favicon.ico',
  themeConfig: {
    navbar: {
      title: 'DocSearch',
      items: [
        { to: '/guides', label: 'Guides', position: 'left' },
        { to: '/reference', label: 'API Reference', position: 'left' },
        { to: '/tutorials', label: 'Tutorials', position: 'left' },
      ],
    },
  },
};
