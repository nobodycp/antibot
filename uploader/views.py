# uploader/views.py

from django.shortcuts import render, redirect
from .models import ArchiveFile
from .forms import ArchiveFileForm

def uploader_files_view(request):
    if request.method == 'POST':
        if 'delete_id' in request.POST:
            ArchiveFile.objects.filter(id=request.POST['delete_id']).delete()
            return redirect('uploader_files')

        form = ArchiveFileForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('uploader_files')
    else:
        form = ArchiveFileForm()

    files = ArchiveFile.objects.all().order_by('-id')
    return render(request, 'files.html', {
        'files': files,
        'form': form
    })
