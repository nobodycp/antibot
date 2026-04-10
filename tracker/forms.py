from django import forms


class AddBlockRuleForm(forms.Form):
    block_type = forms.CharField(required=False, max_length=255)
    block_value = forms.CharField(required=False, strip=True, max_length=512)


class DeleteIpLogForm(forms.Form):
    delete_ip = forms.CharField(required=False, strip=True, max_length=128)
