# Kim Chỉ Nam Dự Án FleetRMW

## Tư Tưởng Gốc

FleetRMW không cố trở thành một DDS nhanh hơn.

FleetRMW là một lớp truyền thông ROS 2-native cho fleet robot lớn, nơi mục tiêu
không phải là gửi được nhiều topic nhất, mà là gửi đúng thông tin có giá trị
nhất cho nhiệm vụ, đúng thời hạn, trong điều kiện mạng hữu hạn và không ổn định.

Nói ngắn:

```text
ROS 2 hiện tại: topic-centric QoS
FleetRMW: fleet-intent-centric QoX
```

## Nguyên Lý Không Được Phá Vỡ

1. Giữ mindset ROS.

   Developer vẫn dùng `rclcpp`, `rclpy`, topic, service, action, lifecycle,
   launch, Nav2, MoveIt, rosbag2 và tooling ROS 2 nhiều nhất có thể.

2. Không expose toàn bộ ROS graph ra fleet.

   Mỗi robot là một local communication island. Bên ngoài chỉ thấy capability,
   state, intent và những flow được phép.

3. Truyền thông là giảm rủi ro nhiệm vụ.

   Một message đáng gửi khi nó làm giảm bất định, giảm rủi ro, tăng khả năng
   hoàn thành task, hoặc cải thiện trải nghiệm vận hành.

4. Realtime qua mạng là một hợp đồng xác suất, không phải lời hứa tuyệt đối.

   FleetRMW không hứa hard realtime qua Internet tùy ý. Nó phải cung cấp SLO đo
   được: p99 latency, stale ratio, deadline miss, task success, QoE.

5. Control và safety-adjacent flow không được bị starvation.

   Video, debug, log, rosbag, visualization không bao giờ được bóp chết command,
   state tươi, hoặc coordination flow quan trọng.

6. Freshness quan trọng hơn completeness.

   Với sensor/video/telemetry realtime, dữ liệu cũ thường vô giá trị. FleetRMW
   ưu tiên dữ liệu mới, drop stale sample có chủ đích, và chỉ retransmit khi dữ
   liệu còn giá trị.

7. QoS không đủ. Cần QoX.

   ```text
   QoS: latency, jitter, loss, throughput
   QoE: operator smoothness, video continuity, control confidence
   QoT: task success, risk reduction, coordination stability
   SAoI: semantic age of useful information
   ```

8. Novelty phải nằm ở semantics truyền thông.

   Không chỉ bọc DDS/Zenoh bằng config. Đóng góp phải nằm ở cách định nghĩa,
   đo, học và tối ưu giá trị thông tin cho fleet.

## Câu Hỏi Dẫn Đường

Khi thiết kế bất kỳ module nào, luôn hỏi:

- Message này giúp task nào?
- Nếu không gửi message này trong 100 ms tới, rủi ro nào tăng?
- Dữ liệu này còn mới hay đã hết giá trị?
- Có robot/operator nào thật sự cần dữ liệu này không?
- Có flow quan trọng hơn đang bị cạnh tranh bandwidth không?
- Có thể gửi semantic delta thay vì raw topic không?
- Quyết định này có làm vi phạm deadline control/state không?

## Định Nghĩa Thành Công

FleetRMW thành công nếu trong workload nhiều robot, mạng xấu, có video/debug
load, nó vẫn giữ được:

- command/control latency thấp ở tail p99/p999;
- state freshness ổn định;
- operator QoE ít freeze/stutter hơn;
- task success cao hơn;
- bandwidth thấp hơn do không forward raw ROS graph;
- discovery/graph overhead thấp hơn DDS native;
- developer vẫn cảm thấy đang viết ROS 2.
