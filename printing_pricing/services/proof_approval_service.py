from typing import Dict, Any, Optional
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from ..models import PrintingOrder, ProofSignOff


class ProofApprovalService:
    """
    خدمة إدارة البروفات الرقمية واعتماد العميل الإلكتروني
    """

    @classmethod
    def generate_proof_request(
        cls,
        order: PrintingOrder,
        proof_file=None,
        user=None
    ) -> Dict[str, Any]:
        """
        إنشاء طلب بروفة رقمية جديد أو تحديث الطلب القائم
        """
        try:
            signoff, created = ProofSignOff.objects.get_or_create(
                order=order,
                defaults={
                    'status': ProofSignOff.ProofStatus.PENDING,
                    'created_by': user,
                    'updated_by': user
                }
            )

            if proof_file:
                signoff.proof_file = proof_file
                signoff.status = ProofSignOff.ProofStatus.PENDING
                signoff.approved_at = None
                signoff.approved_by_name = None
                signoff.save()

            return {
                'success': True,
                'token': str(signoff.token),
                'order_number': order.order_number,
                'status': signoff.status,
                'status_display': signoff.get_status_display(),
                'proof_file_url': signoff.proof_file.url if signoff.proof_file else None,
                'message': _('تم إنشاء رابط اعتماد البروفة بنجاح')
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في إنشاء طلب البروفة')}

    @classmethod
    def approve_proof(
        cls,
        token: str,
        client_name: str,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        اعتماد البروفة الرقمية إلكترونياً من العميل
        """
        try:
            signoff = ProofSignOff.objects.select_related('order').get(token=token)
            
            if signoff.status == ProofSignOff.ProofStatus.APPROVED:
                return {
                    'success': True,
                    'message': _('تم اعتماد البروفة مسبقاً'),
                    'order_number': signoff.order.order_number,
                    'status': signoff.status
                }

            signoff.status = ProofSignOff.ProofStatus.APPROVED
            signoff.approved_by_name = client_name
            signoff.approved_at = timezone.now()
            signoff.client_ip = client_ip
            signoff.save()

            return {
                'success': True,
                'message': _('تم اعتماد البروفة بنجاح، جاري بدء تجهيز زنكات الطباعة'),
                'order_number': signoff.order.order_number,
                'approved_by': client_name,
                'approved_at': signoff.approved_at.strftime('%Y-%m-%d %H:%M')
            }
        except ProofSignOff.DoesNotExist:
            return {'success': False, 'error': _('رمز البروفة غير صالح أو منتهي')}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @classmethod
    def reject_proof(
        cls,
        token: str,
        feedback: str,
        client_name: str,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        رفض البروفة الرقمية مع تسجيل ملاحظات وتعديلات العميل
        """
        try:
            signoff = ProofSignOff.objects.select_related('order').get(token=token)
            
            signoff.status = ProofSignOff.ProofStatus.REJECTED
            signoff.client_feedback = feedback
            signoff.approved_by_name = client_name
            signoff.approved_at = timezone.now()
            signoff.client_ip = client_ip
            signoff.save()

            return {
                'success': True,
                'message': _('تم تسجيل ملاحظاتكم وإعادة توجيهها لفريق التصميم والمونتاج'),
                'order_number': signoff.order.order_number,
                'feedback': feedback
            }
        except ProofSignOff.DoesNotExist:
            return {'success': False, 'error': _('رمز البروفة غير صالح أو منتهي')}
        except Exception as e:
            return {'success': False, 'error': str(e)}
