import matplotlib.pyplot as plt
import numpy as np

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

# 实验数据：角度(度)和对应的光强值
data = [
    (0, 1.045),
    (30, 0.771),
    (60, 0.243),
    (90, 0.003),
    (120, 0.245),
    (150, 0.751),
    (180, 1.050),
    (210, 0.752),
    (240, 0.262),
    (270, 0.016),
    (300, 0.261),
    (330, 0.755),
    (360, 1.053)
]

# 提取角度和光强
angles = [item[0] for item in data]
intensities = [item[1] for item in data]

# 创建图形 - 使用A4纸张大小比例
plt.figure(figsize=(8.27, 5.83))  # A4尺寸 (8.27x5.83英寸)

# 绘制数据点
plt.scatter(angles, intensities, color='red', s=60, label='实验数据点', edgecolors='black', zorder=3)

# 绘制平滑曲线
plt.plot(angles, intensities, color='blue', linewidth=2, label='马吕斯定律曲线', zorder=2)

# 设置坐标轴
plt.xlim(0, 360)
plt.ylim(0, 1.2)
plt.xticks(np.arange(0, 361, 30))
plt.yticks(np.arange(0, 1.3, 0.2))

# 添加网格
plt.grid(True, linestyle='--', alpha=0.7, zorder=1)

# 添加标题和标签
plt.title('马吕斯定律实验曲线', fontsize=16, fontweight='bold')
plt.xlabel('角度 (°)', fontsize=14)
plt.ylabel('相对光强', fontsize=14)

# 添加图例
plt.legend(fontsize=12, loc='upper right')

# 调整布局
plt.tight_layout()

# 保存为高分辨率PNG和PDF格式
plt.savefig('malus_law_curve_print.png', dpi=600, bbox_inches='tight')
plt.savefig('malus_law_curve_print.pdf', dpi=600, bbox_inches='tight')

print('马吕斯定律曲线图已生成并保存为：')
print('1. malus_law_curve_print.png (高分辨率PNG，适合打印)')
print('2. malus_law_curve_print.pdf (PDF格式，适合打印)')