# -*- coding: utf-8 -*-
#---------------------------------------------------------------------
# Name:       Farmland_JsonToFeatureClass.py
# Purpose:    サンプルスクリプト - ArcGIS Pro 環境のマルチプロセスでの処理との時間比較用
#               a)農地の筆界GeoJSONファイルを、都道府県FGDB 内のフィーチャクラスにインサート
#                 × 市区町村のGeoJSONファイル数
# Author:     Kataya @ ESRI Japan
# Created:    2025/03/24
# Copyright:   (c) ESRI Japan Corporation
# ArcGIS Pro Version:   3.3
# Python Version:   3.9
#---------------------------------------------------------------------
import arcpy
import os
import sys
import glob
import datetime

#自前のGeoJSONからフィーチャクラスへの変換するクラスをインポート
from MP_Farmland_JsonToFeatureClass import FarmlandGeojsonToFeaturesEx
#フィールドエイリアスとドメイン設定の補助関数も別名でインポート
from MP_Farmland_JsonToFeatureClass import __alter_field_alias as alter_field_alias
from MP_Farmland_JsonToFeatureClass import __assign_domain as assign_domain

#モジュールを変更した場合に即座に反映されないのでreload を追加
from importlib import reload
reload(sys.modules["MP_Farmland_JsonToFeatureClass"])

# 
# ジオプロセシング ツールボックスの定義
# - テンプレート
#   https://pro.arcgis.com/ja/pro-app/latest/arcpy/geoprocessing_and_python/a-template-for-python-toolboxes.htm
# 
class Toolbox:
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "農地筆ポリゴン変換 サンプルツールボックス"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [AgrilandJsonConvTool2]

# 
# 各ジオプロセシング ツールの定義
# 
class AgrilandJsonConvTool2:
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "01_サンプル_農地筆ポリゴン（GeoJSON形式）_変換ツール"
        self.description = ""

    def getParameterInfo(self):
        """Define the tool parameters."""
        #param0 入力フォルダー（解凍後の都道府県単位のフォルダー）
        #param1 出力フォルダー（処理用テンポラリの市区町村FGDBと最終の都道府県FGDBの保存先：基本的に空のフォルダーを指定）
        param0 = arcpy.Parameter(
            displayName="入力フォルダー（解凍後の都道府県フォルダー）",
            name="input_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")
        param1 = arcpy.Parameter(
            displayName="出力フォルダー（都道府県のFGDBの保存先：空のフォルダーを指定してください）",
            name="out_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")
        params = [param0, param1]
        return params

    def isLicensed(self):
        """Set whether the tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        #入力フォルダーのチェック
        if parameters[0].value:
            infolder = parameters[0].valueAsText
            json_files = glob.glob(infolder + "/*.json") # フルパスのリスト
            if len(json_files) == 0:
                parameters[0].setErrorMessage(u"*.json のファイルが含まれているフォルダーを指定してください。")
        #出力フォルダーのチェック
        if parameters[1].value:
            outfolder = parameters[1].valueAsText
            if len(os.listdir(outfolder)) > 0:
                parameters[1].setErrorMessage(u"空のフォルダーを指定してください。")
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        infolder = parameters[0].valueAsText
        outfolder = parameters[1].valueAsText
        try:
            start = datetime.datetime.now()
            arcpy.AddMessage(u"-- Strat: Farmland_JsonToFeatureClass --:{0}".format(start))
            
            #出力する都道府県のFGDBと出力フィーチャクラスを準備
            foldername = "{0}.gdb".format(os.path.basename(outfolder))
            prefws = os.path.join(outfolder, foldername)
            if not arcpy.Exists(prefws):
                arcpy.management.CreateFileGDB(outfolder, foldername, "CURRENT")
            fcname = "Farmland" #フィーチャクラス名（今回は固定）
            outfc = os.path.join(prefws, fcname)
            
            #入力フォルダーに含まれる *.json ファイルの一覧を取得し、その数だけ変換を繰り返して処理
            arcpy.env.workspace = infolder
            infiles = arcpy.ListFiles("*.json")
            cnt = len(infiles)
            i = 1
            #独自のFarmlandGeojsonToFeaturesEx クラスで変換
            convGeojson = FarmlandGeojsonToFeaturesEx()
            for infile in infiles:
                in_json_file = os.path.join(infolder, infile) #市区町村のGeoJSONファイル
                arcpy.AddMessage(u"-- 変換対象の GeoJSON ファイル : {} -- {} / {} 件目を処理中".format(infile, i, cnt))
                convGeojson.geojson_to_features(in_json_file, outfc)
                i = i + 1
            del convGeojson #後始末
            
            # フィールドエイリアスを設定
            arcpy.AddMessage(u"-- フィールドエイリアスを {} に設定".format(fcname))
            alter_field_alias(outfc)
            
            # コード値ドメインを設定
            arcpy.AddMessage(u"-- land_type_CD のコード値ドメインを {} に設定".format(fcname))
            assign_domain(prefws, outfc)
            
            fin = datetime.datetime.now()
            arcpy.AddMessage(u"-- Finish: Farmland_JsonToFeatureClass --:{0}".format(fin))
            arcpy.AddMessage(u"     Elapsed time:{0}".format(fin-start))
        except:
            arcpy.AddError(u"Exception:{0}".format(sys.exc_info()[2]))
        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return
