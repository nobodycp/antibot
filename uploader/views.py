from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import ArchiveFile
from .forms import ArchiveFileForm
import os
from django.db import models






@login_required
def uploader_files_view(request):
    if request.method == 'POST':
        if 'delete_id' in request.POST:
            ArchiveFile.objects.filter(id=request.POST['delete_id']).delete()
            return redirect('dashboard:uploader_files')  # ✅ هنا التعديل المهم

        form = ArchiveFileForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('dashboard:uploader_files')  # ✅ هنا كمان

    else:
        form = ArchiveFileForm()

    files = ArchiveFile.objects.all().order_by('-id')
    return render(request, 'files.html', {
        'files': files,
        'form': form
    })
