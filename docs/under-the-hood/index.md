---
layout: page
---

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vitepress'

onMounted(() => {
  useRouter().go('/under-the-hood/08-architecture')
})
</script>

Redirecting to [Architecture](08-architecture.md)...
