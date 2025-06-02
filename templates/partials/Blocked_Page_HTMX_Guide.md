
## 📄 HTMX Integration Guide for Blocked Entity Pages (IPs / ISPs / etc)

Use this guide to replicate the interactive HTMX-based table management interface across any blocked-entity page.

---

### ✅ Required Templates

1. **Main Page** – e.g., `blocked_ips.html`
2. **Partial Page** – e.g., `partials/blocked_ips_partial.html`
3. **Table Only** – e.g., `partials/blocked_ips_table.html`
4. **Messages** (optional shared) – e.g., `partials/messages.html`

---

### ✅ Views (`views.py`)

#### 1. Main View
```python
@login_required
def blocked_ips_view(request):
    if request.method == 'POST':
        # Add / Delete / Delete All logic here...

        if request.headers.get("HX-Request"):
            all_ips = BlockedIP.objects.all().order_by('-id')
            paginator = Paginator(all_ips, 20)
            page_number = request.GET.get("page")
            page_obj = paginator.get_page(page_number)
            return render(request, "partials/blocked_ips_partial.html", {
                "blocked_ips": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })
        return redirect("blocked_ips")

    all_ips = BlockedIP.objects.all().order_by('-id')
    paginator = Paginator(all_ips, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "blocked_ips.html", {
        "blocked_ips": page_obj.object_list,
        "page_obj": page_obj
    })
```

#### 2. Partial Page View
```python
@login_required
def blocked_ips_partial(request):
    all_ips = BlockedIP.objects.all().order_by('-id')
    paginator = Paginator(all_ips, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "partials/blocked_ips_partial.html", {
        "blocked_ips": page_obj.object_list,
        "page_obj": page_obj,
        "messages": messages.get_messages(request)
    })
```

#### 3. Table-Only View
```python
@login_required
def blocked_ips_table(request):
    all_ips = BlockedIP.objects.all().order_by('-id')
    paginator = Paginator(all_ips, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "partials/blocked_ips_table.html", {
        "blocked_ips": page_obj.object_list
    })
```

---

### ✅ URLs (`urls.py`)
```python
path("dashboard/blocked-ips/", blocked_ips_view, name="blocked_ips"),
path("dashboard/blocked-ips/partial/", blocked_ips_partial, name="blocked_ips_partial"),
path("dashboard/blocked-ips/table/", blocked_ips_table, name="blocked_ips_table"),
```

---

### ✅ HTML (Main Page Template)
- Use `hx-post` for add/delete
- Use `hx-get` for refresh:
```html
<a href="#" hx-get="{% url 'blocked_ips_table' %}" hx-target="#ip-table-body" hx-swap="outerHTML">
  <!-- Refresh Icon -->
</a>
```

- Include the full wrapper:
```django
{% include 'partials/blocked_ips_partial.html' %}
```

- Use scripts:
```html
<script>
function confirmDeleteAll(e) {
  if (!confirm("Are you sure you want to delete all IPs?")) {
    e.preventDefault();
  }
}

document.addEventListener('htmx:afterSwap', function (e) {
  if (e.target.id === 'blocked-ips-wrapper') {
    setTimeout(() => {
      const msgBox = document.getElementById("htmx-messages");
      if (msgBox) msgBox.innerHTML = '';
    }, 3000);
  }
});
</script>
```

---

### ✅ Partial: `blocked_ips_partial.html`
```django
<div id="blocked-ips-wrapper">
  {% include 'partials/messages.html' %}
  <div class="rounded overflow-hidden border">
    <table>
      <thead>...</thead>
      {% include 'partials/blocked_ips_table.html' %}
    </table>
  </div>
  {% if page_obj.has_other_pages %}
    <!-- Pagination -->
  {% endif %}
</div>
```

---

### ✅ Table: `blocked_ips_table.html`
```django
<tbody id="ip-table-body">
  {% for ip in blocked_ips %}
    <tr>...</tr>
  {% empty %}
    <tr><td colspan="2">No blocked IPs</td></tr>
  {% endfor %}
</tbody>
```

---

📌 استخدم نفس النمط لأي صفحة مثل Blocked Hostnames, ISPs, Countries... إلخ.

جاهز للتطبيق فورًا بدون إعادة اختراع العجلة 🚀
