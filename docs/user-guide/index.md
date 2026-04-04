---
layout: page
---

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vitepress'

onMounted(() => {
  useRouter().go('/user-guide/01-setup')
})
</script>

Redirecting to [Setup](01-setup.md)...
