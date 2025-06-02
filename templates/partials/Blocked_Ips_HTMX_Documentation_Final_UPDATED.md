# 📄 توثيق إعداد جدول Blocked IPs باستخدام HTMX وDjango Messages (مُحدّث)

---

## ✅ التحديثات الأخيرة (يونيو 2025)
- ✅ دعم التنقل: ← Prev | Page X of Y | Next →
- ✅ فصل الجزء القابل للتحديث إلى `partials/blocked_ips_partial.html`
- ✅ تقليل عدد العناصر لكل صفحة إلى 20
- ✅ الحفاظ على أداء سريع عند عرض IPs كثيرة

---

## 📁 الملفات

### 1. blocked_ips.html
يحتوي على:
- نموذج إضافة IP
- زر حذف الكل
- زر تحديث الجدول
- البحث
- عنصر `<div id="blocked-ips-wrapper">` الذي يُحدثه HTMX عبر partial

```django
{% include 'partials/blocked_ips_partial.html' %}
```

---

### 2. partials/blocked_ips_partial.html

```django
<div id="blocked-ips-wrapper">
  {% include "partials/blocked_ips_messages.html" %}
  <div class="rounded overflow-hidden border border-zinc-700">
    <table class="w-full bg-zinc-800 text-xs">
      <thead class="bg-zinc-700 text-left text-zinc-300 uppercase tracking-wide">
        <tr>
          <th class="px-3 py-2">IP Address</th>
          <th class="px-3 py-2 text-right">Delete</th>
        </tr>
      </thead>
      {% include "partials/blocked_ips_table.html" %}
    </table>
  </div>

  <!-- Pagination -->
  <div class="mt-4 flex gap-2 text-xs">
    {% if page_obj.has_previous %}
      <a href="{% url 'blocked_ips_partial' %}?page={{ page_obj.previous_page_number }}"
         hx-get="{% url 'blocked_ips_partial' %}?page={{ page_obj.previous_page_number }}"
         hx-target="#blocked-ips-wrapper" hx-swap="outerHTML"
         class="text-blue-400 hover:underline">← Prev</a>
    {% endif %}

    <span class="text-zinc-400">Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}</span>

    {% if page_obj.has_next %}
      <a href="{% url 'blocked_ips_partial' %}?page={{ page_obj.next_page_number }}"
         hx-get="{% url 'blocked_ips_partial' %}?page={{ page_obj.next_page_number }}"
         hx-target="#blocked-ips-wrapper" hx-swap="outerHTML"
         class="text-blue-400 hover:underline">Next →</a>
    {% endif %}
  </div>
</div>
```

---

## ⚙️ views.py

```python
from django.core.paginator import Paginator

def blocked_ips_view(request):
    ...
    all_ips = BlockedIP.objects.all().order_by('-id')
    paginator = Paginator(all_ips, 20)  # ← هنا التعديل إلى 20 فقط
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if request.headers.get("HX-Request"):
        return render(request, "partials/blocked_ips_partial.html", {
            "blocked_ips": page_obj.object_list,
            "page_obj": page_obj,
            "messages": messages.get_messages(request)
        })
    return render(request, "blocked_ips.html", {
        "blocked_ips": page_obj.object_list,
        "page_obj": page_obj
    })
```

---

## ✅ جاهز للتوسعة
يمكن تطبيق نفس النظام بسهولة على:
- Blocked Hostnames
- Denied Logs
- Allowed Visitors

