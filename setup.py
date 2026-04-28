from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="delhivery_integration",
    version="1.0.0",
    description="Delhivery courier integration with multi-warehouse delivery partner support",
    author="Reformiqo",
    author_email="info@reformiqo.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
