"""Action permissions limited by the actor's Chương IV role."""

COMMON = {
    'traffic.view': 'Xem tình trạng, lịch sử và bản đồ',
    'forecast.view': 'Xem dự báo theo ngày và giờ',
    'routes.search': 'Tìm tuyến đường',
    'favorites.view': 'Xem hành trình đã lưu',
    'favorites.add': 'Lưu hành trình',
    'favorites.delete': 'Bỏ hành trình đã lưu',
    'warnings.view': 'Xem cảnh báo đã công bố',
    'alerts.view': 'Xem thông báo cá nhân',
    'alerts.follow': 'Thêm hoặc bỏ theo dõi tuyến',
    'alerts.read': 'Đánh dấu thông báo đã đọc',
    'reports.view': 'Xem phản ánh của mình',
    'reports.add': 'Gửi phản ánh',
}
MANAGEMENT = {
    'monitor.view': 'Xem giám sát và trạng thái nguồn',
    'monitor.camera': 'Xem hình ảnh camera',
    'incidents.view': 'Xem hồ sơ phản ánh được phân công',
    'incidents.accept': 'Tiếp nhận phản ánh',
    'incidents.verify': 'Xác minh phản ánh',
    'incidents.edit': 'Sửa thông tin sự cố',
    'incidents.progress': 'Cập nhật tiến độ',
    'incidents.reject': 'Từ chối phản ánh',
    'incidents.resolve': 'Hoàn tất phản ánh',
    'publication.view': 'Xem hồ sơ cảnh báo',
    'publication.add': 'Tạo bản nháp cảnh báo',
    'publication.edit': 'Sửa bản nháp cảnh báo',
    'publication.verify': 'Xác minh bản nháp',
    'publication.publish': 'Phát hành cảnh báo',
    'publication.cancel': 'Hủy bản nháp cảnh báo',
    'rules.view': 'Xem quy tắc cảnh báo',
    'rules.add': 'Tạo quy tắc',
    'rules.edit': 'Sửa quy tắc',
    'rules.test': 'Kiểm tra quy tắc',
    'rules.toggle': 'Bật hoặc tắt quy tắc',
    'rules.delete': 'Xóa quy tắc',
    'analytics.view': 'Xem thống kê và đánh giá dự báo theo giờ',
    'analytics.export': 'Xuất báo cáo giao thông',
    'sources.manage': 'Cấu hình nguồn và tiếp nhận dữ liệu giao thông',
    'network.manage': 'Cấu hình đoạn đường và camera',
    'models.manage': 'Chuẩn bị dữ liệu và huấn luyện mô hình',
    'diagnostics.view': 'Xem trạng thái dịch vụ và nhật ký vận hành',
}
ADMINISTRATION = {key: MANAGEMENT[key] for key in ('sources.manage','network.manage','models.manage','diagnostics.view')}
PUBLIC = {'traffic.view', 'forecast.view', 'routes.search', 'warnings.view'}
PARENTS = {
    **{key: key.split('.')[0]+'.view' for key in MANAGEMENT if key.split('.')[0]+'.view' in MANAGEMENT},
    'favorites.delete': 'favorites.view', 'favorites.add': 'routes.search',
    'alerts.follow': 'alerts.view', 'alerts.read': 'alerts.view',
}


def choices(role):
    if role == 'admin':
        return ADMINISTRATION
    if role == 'analyst':
        return {**COMMON, **MANAGEMENT}
    return COMMON if role == 'user' else {}


def granted(role, assigned):
    return [key for key in choices(role) if allows(role, assigned, key)]


def allows(role, assigned, key):
    return key in choices(role) and (assigned is None or key in assigned and PARENTS.get(key,key) in assigned)
