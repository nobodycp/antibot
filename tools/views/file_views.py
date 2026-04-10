import os

from django.contrib import messages
from django.shortcuts import redirect, render

from core.decorators import superuser_required

from ..forms import ArchiveFileForm
from ..models import ArchiveFile


@superuser_required
def uploader_files_view(request):
    if request.method == 'POST':
        if 'delete_id' in request.POST:
            try:
                file_obj = ArchiveFile.objects.get(id=request.POST['delete_id'])

                # ✅ حذف الملف الفعلي من media/zips
                if file_obj.zip_file and os.path.isfile(file_obj.zip_file.path):
                    os.remove(file_obj.zip_file.path)

                # ✅ حذف السجل من قاعدة البيانات
                file_obj.delete()

                messages.error(request, "File deleted successfully.")
            except ArchiveFile.DoesNotExist:
                messages.error(request, "File not found.")

            return redirect('tools:uploader_files')

        # ✅ رفع ملف جديد
        form = ArchiveFileForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "File uploaded successfully.")
            return redirect('tools:uploader_files')

    else:
        form = ArchiveFileForm()

    files = ArchiveFile.objects.all().order_by('-id')
    return render(request, 'tools/files.html', {
        'files': files,
        'form': form
    })
